import app as myapp
from flask import session

myapp.app.config['TESTING'] = True

with myapp.app.test_client() as client:
    with client.session_transaction() as sess:
        sess['role'] = 'admin'
        sess['user_id'] = 'admin_id'
        sess['username'] = 'admin'
    
    try:
        response = client.get('/admin/generate_qr/DSA_2024')
        print("STATUS:", response.status_code)
        text = response.get_data(as_text=True)
        if 'img src="data:image/png;base64' in text:
            print("QR found in output HTML!")
        else:
            print("QR MISSING! HTML snippet:")
            print(text[:500])
    except Exception as e:
        import traceback
        traceback.print_exc()
