import qrcode
import base64
from io import BytesIO

print("Generating QR...")
qr = qrcode.QRCode(version=1, box_size=10, border=5)
qr.add_data("test:data:123")
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")

img_buffer = BytesIO()
img.save(img_buffer, format='PNG')
img_str = base64.b64encode(img_buffer.getvalue()).decode()
print("Success!")
print(img_str[:20])
