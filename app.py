from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import qrcode
from io import BytesIO
import pandas as pd
from datetime import datetime
from models import Database
from config import Config
from werkzeug.security import generate_password_hash
from functools import wraps

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

db = Database()

# Pre-populate DSA class with 30 students
def init_dsa_class():
    if db.classes.find_one({'class_id': 'DSA_2024'}):
        return
    
    students = []
    indian_names = [
        "Aarav Sharma", "Vihaan Patel", "Arjun Singh", "Reyansh Gupta", "Aryan Kumar",
        "Advik Verma", "Mohammed Khan", "Ishaan Joshi", "Dhruv Mishra", "Kabir Yadav",
        "Rudra Chauhan", "Ayaan Reddy", "Vihaan Desai", "Arnav Jain", "Kian Malhotra",
        "Aarush Agarwal", "Devansh Nair", "Pranav Iyer", "Rohan Kapoor", "Sai Krishna",
        "Tejas Menon", "Yash Rajput", "Aditya Shetty", "Bhavesh Thakur", "Chirag Pawar",
        "Divyansh Solanki", "Eshan Trivedi", "Faizan Qureshi", "Gaurav Saxena", "Harsh Rana"
    ]
    
    for i, name in enumerate(indian_names):
        roll_no = f"2201010{i+1:03d}"
        students.append({
            'name': name,
            'roll_no': roll_no,
            'id': roll_no
        })
    
    db.classes.insert_one({
        'class_id': 'DSA_2024',
        'name': 'Data Structures & Algorithms - B.Tech CSE',
        'college': 'K.R. Mangalam University',
        'students': students,
        'created_at': datetime.now()
    })

@app.before_request
def sync_dynamic_roles():
    """Forces the user session to synchronize with the live MongoDB tier to prevent stale credential caching when Admin modifies their permissions."""
    if 'username' in session and request.endpoint and 'static' not in request.endpoint:
        live_user = db.users.find_one({'username': session['username']})
        if live_user and 'role' in live_user:
            session['role'] = live_user['role']

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'student')
        username = request.form['username']
        password = request.form['password']
        success, user, msg = db.authenticate_user(username, password, login_type)
        
        if success and user:
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user['role']
            session['name'] = user.get('name', '')
            
            if user['role'] in ['admin', 'teacher']:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_attendance'))
        else:
            return render_template('login.html', error=msg)
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    classes = list(db.classes.find({}, {'_id': 0, 'class_id': 1, 'name': 1}))
    if request.method == 'POST':
        register_type = request.form.get('register_type', 'student')
        
        if register_type == 'student':
            name = request.form['name']
            roll_no = request.form['roll_no']
            course = request.form['course']
            semester = request.form['semester']
            class_id = request.form['class_id']
            password = request.form['password']
            
            success, msg = db.register_user(name, roll_no, semester, course, class_id, password, {})
        else:
            name = request.form['name']
            username = request.form['username']
            department = request.form['department']
            password = request.form['password']
            
            success, msg = db.register_teacher(name, username, department, password, {})
        
        if success:
            return render_template('register.html', success=msg, classes=classes)
        else:
            return render_template('register.html', error=msg, classes=classes)
            
    return render_template('register.html', classes=classes)

@app.route('/admin/approvals')
def admin_approvals():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    pending_students, pending_teachers = db.get_pending_users()
    return render_template('admin_approvals.html', pending_students=pending_students, pending_teachers=pending_teachers)

@app.route('/api/approve_user', methods=['POST'])
def approve_user():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    success, msg = db.approve_user(data['username'])
    return jsonify({'success': success, 'message': msg})

@app.route('/api/reject_user', methods=['POST'])
def reject_user():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    success, msg = db.reject_user(data['username'])
    return jsonify({'success': success, 'message': msg})

@app.route('/admin/users')
def user_management():
    # Strict lock: ONLY the original root 'admin' username accesses this endpoint
    if 'role' not in session or session.get('username') != 'admin':
        return redirect(url_for('admin_dashboard'))
        
    all_users = db.get_all_users()
    students = [u for u in all_users if u.get('role') == 'student']
    teachers = [u for u in all_users if u.get('role') == 'admin' or u.get('role') == 'teacher']
    
    return render_template('user_management.html', students=students, teachers=teachers)

@app.route('/api/update_role', methods=['POST'])
def update_user_role():
    if 'role' not in session or session.get('username') != 'admin':
        return jsonify({'success': False, 'message': 'Root Authorization Required.'}), 401
        
    data = request.json
    db.update_user_role(data['username'], data['role'])
    return jsonify({'success': True})

@app.route('/api/delete_user/<username>', methods=['POST'])
def delete_user(username):
    if 'role' not in session or session.get('username') != 'admin':
        return jsonify({'success': False, 'message': 'Root Authorization Required.'}), 401
    
    db.delete_user(username)
    return jsonify({'success': True})

@app.route('/api/update_password', methods=['POST'])
def update_user_password():
    if 'role' not in session or session.get('username') != 'admin':
        return jsonify({'success': False, 'message': 'Root Authorization Required.'}), 401
        
    data = request.json
    username = data.get('username')
    new_password = data.get('password')
    
    if not username or not new_password:
        return jsonify({'success': False, 'message': 'Invalid data'})
        
    db.update_user_password(username, new_password)
    return jsonify({'success': True, 'message': 'Password forcibly updated.'})

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'role' not in session or session['role'] not in ['admin', 'teacher']:
        return redirect(url_for('login'))
    
    classes = list(db.classes.find({}, {'_id': 0}))
    dates, counts = db.get_attendance_stats()
    
    return render_template('admin_dashboard.html', classes=classes, chart_dates=dates, chart_counts=counts)

@app.route('/create_class', methods=['GET', 'POST'])
def create_class():
    if 'role' not in session or session['role'] not in ['admin', 'teacher']:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        subject = request.form['subject']
        topic = request.form['topic']
        degree = request.form['degree']
        semester = request.form['semester']
        date_time = request.form['date_time']
        
        success, class_id = db.create_new_class(subject, degree, semester, topic, date_time)
        return redirect(url_for('admin_dashboard'))
        
    return render_template('create_class.html')

@app.route('/edit_class/<class_id>', methods=['GET', 'POST'])
def edit_class(class_id):
    if 'role' not in session or session['role'] not in ['admin', 'teacher']:
        return redirect(url_for('login'))
        
    class_data = db.get_class(class_id)
    if not class_data:
        return redirect(url_for('admin_dashboard'))
        
    if request.method == 'POST':
        name = request.form['name']
        college = request.form['college']
        date_time = request.form.get('date_time', class_data.get('date_time', ''))
        
        db.update_class(class_id, name, college, date_time)
        return redirect(url_for('admin_dashboard'))
        
    return render_template('edit_class.html', cls=class_data)

@app.route('/api/delete_class/<class_id>', methods=['POST'])
def delete_class(class_id):
    if 'role' not in session or session['role'] not in ['admin', 'teacher']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    db.delete_class(class_id)
    return jsonify({'success': True})

@app.route('/admin/generate_qr/<class_id>')
def generate_qr(class_id):
    if 'role' not in session or session['role'] not in ['admin', 'teacher']:
        return redirect(url_for('login'))
    
    session_id = db.get_active_session(class_id, is_manual=False)
    qr_data = db.generate_session_qr(class_id, session_id)
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for template
    import base64
    from io import BytesIO
    img_buffer = BytesIO()
    img.save(img_buffer, format='PNG')
    img_str = base64.b64encode(img_buffer.getvalue()).decode()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('generate_qr.html', 
                         qr_img=img_str,
                         session_id=session_id,
                         class_id=class_id,
                         current_time=current_time)

@app.route('/admin/manual_session/<class_id>')
def manual_session(class_id):
    if 'role' not in session or session['role'] not in ['admin', 'teacher']:
        return redirect(url_for('login'))
    
    session_id = db.get_active_session(class_id, is_manual=True)
    return redirect(url_for('attendance_view', class_id=class_id, session_id=session_id))

@app.route('/admin/attendance/<class_id>/<session_id>')
def attendance_view(class_id, session_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    students = db.get_class_students(class_id)
    attendance_data = db.get_attendance_report(class_id, session_id)
    
    # Create attendance status map
    attendance_map = {item['student_id']: item['status'] for item in attendance_data}
    
    student_list = []
    for student in students:
        status = attendance_map.get(student['id'], 'absent')
        student_list.append({
            **student,
            'status': status
        })
    
    return render_template('attendance_view.html', 
                         students=student_list,
                         class_id=class_id,
                         session_id=session_id)

@app.route('/api/get_live_attendance/<class_id>/<session_id>')
def get_live_attendance(class_id, session_id):
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({})
    attendance_data = db.get_attendance_report(class_id, session_id)
    return jsonify({item['student_id']: item['status'] for item in attendance_data})

@app.route('/api/mark_attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    student_id = data['student_id']
    class_id = data['class_id']
    session_id = data['session_id']
    ip = db.get_client_ip()
    
    success, message = db.mark_attendance_qr(student_id, class_id, session_id, ip)
    return jsonify({'success': success, 'message': message})

@app.route('/api/update_attendance', methods=['POST'])
def update_attendance():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    student_id = data['student_id']
    class_id = data['class_id']
    session_id = data['session_id']
    status = data['status']
    
    db.update_attendance_manual(student_id, class_id, session_id, status)
    return jsonify({'success': True, 'message': 'Updated successfully'})

@app.route('/student/attendance')
def student_attendance():
    if 'role' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
        
    classes = list(db.classes.find({}, {'_id': 0, 'class_id': 1, 'name': 1}))
    return render_template('student_login.html', classes=classes)

@app.route('/api/student/history/<class_id>')
def api_student_history(class_id):
    if 'role' not in session or session.get('role') != 'student':
        return jsonify({'success': False, 'message': 'Unauthorized payload restrictions.'}), 401
    
    student_id = session.get('username')
    history_data = db.get_student_history(student_id, class_id)
    return jsonify({'success': True, 'history': history_data})

@app.route('/api/scan_qr', methods=['POST'])
def scan_qr():
    data = request.json
    qr_data = data['qr_data']
    ip = db.get_client_ip()
    
    if not db.is_allowed_network(ip):
        return jsonify({'success': False, 'message': 'Please connect to college WiFi'})
    
    # Parse QR data: class_id:session_id:timestamp
    parts = qr_data.split(':')
    if len(parts) < 2:
        return jsonify({'success': False, 'message': 'Invalid QR code'})
    
    class_id, session_id = parts[0], parts[1]
    student_id = session.get('username')  # MUST USE USERNAME (Roll_no) MATCHING DB
    
    success, message = db.mark_attendance_qr(student_id, class_id, session_id, ip)
    return jsonify({'success': success, 'message': message})

@app.route('/api/mark_with_code', methods=['POST'])
def mark_with_code():
    if 'role' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json
    session_code = data.get('code', '').strip()
    ip = db.get_client_ip()
    student_id = session.get('username')
    
    if not db.is_allowed_network(ip):
        return jsonify({'success': False, 'message': 'Please connect to college WiFi'})
        
    if not session_code:
        return jsonify({'success': False, 'message': 'Code cannot be empty'})
        
    class_id = ""
    session_id = session_code
    
    # Allow full QR data or strictly session_id
    if ":" in session_code:
        parts = session_code.split(':')
        class_id = parts[0]
        session_id = parts[1]
    else:
        # Deduct class_id from session_id
        parts = session_code.rsplit('_', 1)
        if len(parts) == 2:
            if parts[0].endswith('_manual'):
                class_id = parts[0][:-7]
            else:
                class_id = parts[0]
        else:
            return jsonify({'success': False, 'message': 'Invalid session code'})
            
    success, message = db.mark_attendance_qr(student_id, class_id, session_id, ip)
    return jsonify({'success': success, 'message': message})

@app.route('/api/upload_roster', methods=['POST'])
def upload_roster():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Empty file'})
        
    try:
        # Utilize powerful pandas parser for multidimensional Excel processing
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
            
        success, msg = db.bulk_upload_whitelist(df)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server Parsing Error: {str(e)}'})

@app.route('/download_csv/<class_id>/<session_id>')
def download_csv(class_id, session_id):
    attendance_data = db.get_attendance_report(class_id, session_id)
    students = db.get_class_students(class_id)
    
    student_map = {s['id']: s['name'] for s in students}
    
    df = pd.DataFrame(attendance_data)
    if not df.empty:
        df['student_name'] = df['student_id'].map(student_map)
        if 'timestamp' not in df.columns:
            df['timestamp'] = 'Manual Entry'
        df = df[['student_name', 'student_id', 'status', 'timestamp']]
    
    csv_io = df.to_csv(index=False)
    return send_file(
        BytesIO(csv_io.encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_{class_id}_{session_id}.csv'
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    db.create_admin()
    init_dsa_class()
    app.run(debug=True)