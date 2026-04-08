// Update attendance status
document.addEventListener('DOMContentLoaded', function() {
    const presentBtns = document.querySelectorAll('.present-btn');
    const absentBtns = document.querySelectorAll('.absent-btn');
    
    presentBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            updateAttendance(this.dataset.id, 'present');
        });
    });
    
    absentBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            updateAttendance(this.dataset.id, 'absent');
        });
    });
    
    updateCounts();
});

function updateAttendance(studentId, status) {
    fetch('/api/update_attendance', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            student_id: studentId,
            class_id: window.location.pathname.split('/')[3],
            session_id: window.location.pathname.split('/')[4],
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload(); // Refresh to update UI
        }
    });
}

function updateCounts() {
    const presentCount = document.querySelectorAll('.table-success').length;
    const absentCount = document.querySelectorAll('.table-danger').length;
    
    document.getElementById('present-count').textContent = presentCount;
    document.getElementById('absent-count').textContent = absentCount;
}

// Network status check (simplified for demo)
function checkNetworkStatus() {
    // In production, implement actual IP checking
    document.getElementById('network-status').textContent = 'College WiFi Connected';
}