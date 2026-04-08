from pymongo import MongoClient
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import ipaddress

class Database:
    def __init__(self):
        self.client = MongoClient('mongodb+srv://quantumvista:aJoWTicfsSkXwAaX@quantumvista.znokils.mongodb.net/')
        self.db = self.client['smart_attendance']
        self.users = self.db['users']
        self.attendance = self.db['attendance']
        self.classes = self.db['classes']
        self.settings = self.db['settings']
        self.sessions = self.db.sessions
        self.allowed_users = self.db.allowed_users # Core Roster Whitelist DB
        
        # Create indexes
        self.users.create_index('username', unique=True)
    
    def get_client_ip(self):
        # In production, get from request.environ
        return '192.168.1.100'  # Demo IP
    
    def is_allowed_network(self, ip):
        allowed_networks = self.settings.find_one({}) or {'networks': ['192.168.1.0/24']}
        networks = allowed_networks.get('networks', [])
        
        try:
            client_ip = ipaddress.ip_address(ip)
            for network in networks:
                if client_ip in ipaddress.ip_network(network):
                    return True
            return False
        except:
            return False
    
    def create_admin(self):
        if self.users.find_one({'role': 'admin'}):
            return
        self.users.insert_one({
            'username': 'admin',
            'password': generate_password_hash('admin123'),
            'role': 'admin',
            'name': 'Teacher Admin'
        })
    
    def authenticate_user(self, username, password, login_type='student'):
        query = {'username': username}
        
        # Strictly limit the type of account accessible per tab to avoid numerical ID collision
        if login_type == 'student':
            query['role'] = 'student'
        else:
            query['role'] = {'$in': ['teacher', 'admin']}
            
        user = self.users.find_one(query)
        if user and check_password_hash(user['password'], password):
            # Because Option B Auto-Approves, we verify the approved layer
            if user.get('status') == 'pending':
                return False, user, "Your account is awaiting manual review."
            return True, user, "Login successful"
        return False, None, "Invalid Credentials. Did you select the correct Student/Faculty tab?"
        
    def check_whitelist(self, username):
        """Validates if a targeted ID was previously authorized by Admin."""
        return self.allowed_users.find_one({'username': username})
        
    def bulk_upload_whitelist(self, df):
        """Processes the Pandas dataframe pushing credentials to locked DB."""
        inserted = 0
        df = df.fillna('')
        
        def get_val(row_dict, keys):
            for k in keys:
                if k in row_dict: return str(row_dict[k])
            return ''
            
        for _, row in df.iterrows():
            row_dict = {str(k).lower().strip(): v for k, v in row.items()}
            
            username = get_val(row_dict, ['username', 'student_id', 'roll no', 'roll number', 'id', 'rollno']).strip()
            role = get_val(row_dict, ['role', 'type']).strip().lower() or 'student'
            if not username: continue
            
            self.allowed_users.update_one(
                {'username': username},
                {'$set': {
                    'username': username,
                    'name': get_val(row_dict, ['name', 'student_name', 'full name']).strip(),
                    'role': role,
                    'class_id': get_val(row_dict, ['classid', 'class_id', 'class']).strip(),
                    'email': get_val(row_dict, ['email']).strip()
                }},
                upsert=True
            )
            inserted += 1
        return True, f"Successfully mapped and whitelisted {inserted} user credentials to database!"

    def register_user(self, name, roll_no, semester, course, class_id, password, extra_info=None):
        # Strict Roster Validation Security
        whitelist_entry = self.check_whitelist(roll_no)
        if not whitelist_entry:
            return False, "REGISTRATION BLOCKED: Your Roll Number is not authorized natively in the University Registry. Contact Admin."
            
        if self.users.find_one({'username': roll_no}):
            return False, "This Roll Number has already claimed their account."
            
        actual_class = whitelist_entry.get('class_id') or class_id
        
        user_doc = {
            'username': roll_no,
            'password': generate_password_hash(password),
            'role': 'student',
            'status': 'pending', # Option A Enforcement -> Sent to Admin Approval Grid
            'name': name,
            'roll_no': roll_no,
            'semester': semester,
            'course': course,
            'class_id': actual_class,
            'extra_info': extra_info or {}
        }
        
        self.users.insert_one(user_doc)
        return True, "Registration Authenticated via Excel! Your application has been sent to Admin for final approval."

    def get_pending_users(self):
        # We can extract them by role
        users = list(self.users.find({'status': 'pending'}))
        students = [u for u in users if u.get('role') == 'student']
        # Teachers might be requested as 'admin' pending, or 'teacher' pending
        teachers = [u for u in users if u.get('role') in ['admin', 'teacher']]
        return students, teachers

    def register_teacher(self, name, username, department, password, extra_info=None):
        whitelist_entry = self.check_whitelist(username)
        if not whitelist_entry:
            return False, "REGISTRATION BLOCKED: Faculty ID is not recognized in Admin Roster Data."
            
        if self.users.find_one({'username': username}):
            return False, "Faculty ID already claimed."
        
        self.users.insert_one({
            'username': username,
            'password': generate_password_hash(password),
            'role': whitelist_entry.get('role') if whitelist_entry.get('role') in ['admin', 'teacher'] else 'teacher',
            'status': 'pending', # Sent to Approvals grid
            'name': name,
            'department': department,
            'extra_info': extra_info or {}
        })
        return True, "Faculty account authenticated via Excel! Awaiting Admin Approval."

    def get_all_users(self):
        return list(self.users.find({'status': 'approved'}))
        
    def update_user_role(self, username, new_role):
        self.users.update_one(
            {'username': username},
            {'$set': {'role': new_role}}
        )
        return True

    def update_user_password(self, username, new_password):
        self.users.update_one(
            {'username': username},
            {'$set': {'password': generate_password_hash(new_password)}}
        )
        return True

    def delete_user(self, username):
        self.users.delete_one({'username': username})
        self.allowed_users.delete_one({'username': username})
        return True

    def approve_user(self, username):
        user = self.users.find_one({'username': username})
        if not user: return False, "User not found"
        
        class_id = user.get('class_id')
        if class_id:
            class_data = self.classes.find_one({'class_id': class_id})
            if class_data:
                existing = [s for s in class_data.get('students', []) if s['id'] == user['roll_no']]
                if not existing:
                    self.classes.update_one(
                        {'class_id': class_id},
                        {'$push': {'students': {
                            'id': user['roll_no'],
                            'name': user['name'],
                            'roll_no': user['roll_no']
                        }}}
                    )
        
        self.users.update_one({'username': username}, {'$set': {'status': 'approved'}})
        return True, "User approved successfully"

    def reject_user(self, username):
        result = self.users.delete_one({'username': username})
        return result.deleted_count > 0, "User rejected and removed"
    
    def generate_session_qr(self, class_id, session_id):
        qr_data = f"{class_id}:{session_id}:{datetime.now().isoformat()}"
        return qr_data
    
    def mark_attendance_qr(self, student_id, class_id, session_id, ip):
        if not self.is_allowed_network(ip):
            return False, "Not connected to college WiFi"
        
        now = datetime.now()
        attendance_data = {
            'student_id': student_id,
            'class_id': class_id,
            'session_id': session_id,
            'timestamp': now,
            'date': now.strftime('%Y-%m-%d'),
            'status': 'present',
            'method': 'qr_scan',
            'ip': ip
        }
        
        # Check duplicate
        if self.attendance.find_one({
            'student_id': student_id,
            'class_id': class_id,
            'session_id': session_id
        }):
            return False, "Attendance already marked"
        
        self.attendance.insert_one(attendance_data)
        return True, "Attendance marked successfully"
    
    def get_class_students(self, class_id):
        class_data = self.classes.find_one({'class_id': class_id})
        return class_data.get('students', [])
    
    def update_attendance_manual(self, student_id, class_id, session_id, status):
        self.attendance.update_one(
            {'student_id': student_id, 'class_id': class_id, 'session_id': session_id},
            {
                '$set': {'status': status, 'method': 'manual'},
                '$setOnInsert': {'timestamp': datetime.now()}
            },
            upsert=True
        )
    
    def get_attendance_report(self, class_id, session_id):
        return list(self.attendance.find({
            'class_id': class_id,
            'session_id': session_id
        }))

    def get_student_history(self, student_id, class_id):
        """Combines all class sessions natively and matches against student ledger for absence calculations."""
        from datetime import timedelta
        
        # Pull all distinct sessions natively from the attendance ledger to bypass missing session nodes
        unique_sessions = self.attendance.distinct('session_id', {'class_id': class_id})
        
        history = []
        now = datetime.now()
        active_window = now - timedelta(hours=4)
        
        for s_id in unique_sessions:
            sample_record = self.attendance.find_one({'session_id': s_id})
            if not sample_record: continue
            
            student_record = self.attendance.find_one({
                'session_id': s_id,
                'student_id': student_id
            })
            
            # Reconstruct the raw timestamp from the sample payload
            raw_date = sample_record.get('timestamp')
            if isinstance(raw_date, datetime):
                date_str = raw_date.strftime('%Y-%m-%d <small class="text-muted">%I:%M %p</small>')
            else:
                date_str = sample_record.get('date', str(s_id))
            
            if student_record:
                status = 'Present'
            else:
                # If the session was mapped within the active 4-hour window, it's currently running
                status = 'Pending' if isinstance(raw_date, datetime) and raw_date >= active_window else 'Absent'
            
            history.append({
                'date': date_str,
                'status': status,
                'timestamp': student_record['timestamp'].strftime('%I:%M:%S %p') if student_record else '-'
            })
            
        # Reverse sort to throw the newest sessions to the top
        history.sort(key=lambda x: x.get('date', ''), reverse=True)
        return history

    def get_attendance_stats(self):
        pipeline = [
            {"$match": {"status": "present"}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}},
            {"$limit": 7}
        ]
        results = list(self.attendance.aggregate(pipeline))
        dates = [r['_id'] for r in results]
        counts = [r['count'] for r in results]
        return dates, counts
        
    def create_new_class(self, subject, degree, semester, topic, date_time):
        class_id = f"{degree.replace(' ', '')}_{semester.replace(' ', '')}_{int(datetime.now().timestamp())}"
        
        assigned_students = []
        if degree == "B.Tech" and semester == "8th Sem":
            dsa_template = self.classes.find_one({'class_id': 'DSA_2024'})
            if dsa_template:
                assigned_students = dsa_template.get('students', [])
                
        self.classes.insert_one({
            'class_id': class_id,
            'name': f"{subject} - {topic}",
            'college': f"Degree: {degree} | Sem: {semester}",
            'date_time': date_time,
            'students': assigned_students,
            'created_at': datetime.now()
        })
        return True, class_id

    def get_class(self, class_id):
        return self.classes.find_one({'class_id': class_id}, {'_id': 0})
        
    def update_class(self, class_id, name, college, date_time):
        self.classes.update_one(
            {'class_id': class_id},
            {'$set': {
                'name': name,
                'college': college,
                'date_time': date_time
            }}
        )
        return True

    def delete_class(self, class_id):
        self.classes.delete_one({'class_id': class_id})
        self.attendance.delete_many({'class_id': class_id})
        return True
        
    def get_active_session(self, class_id, is_manual=False):
        cls = self.classes.find_one({'class_id': class_id})
        session_key = 'active_manual_session' if is_manual else 'active_qr_session'
        
        if cls and cls.get(session_key):
            parts = cls[session_key].split('_')
            try:
                timestamp = int(parts[-1])
                # Reuse if session is less than 4 hours old
                if (datetime.now().timestamp() - timestamp) < 14400: 
                    return cls[session_key]
            except ValueError:
                pass
                
        # Generate new session ID
        suffix = f"manual_{int(datetime.now().timestamp())}" if is_manual else f"{int(datetime.now().timestamp())}"
        session_id = f"{class_id}_{suffix}"
        self.classes.update_one({'class_id': class_id}, {'$set': {session_key: session_id}})
        return session_id