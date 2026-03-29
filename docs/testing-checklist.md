# Manual Testing Checklist

เช็กลิสต์นี้ใช้สำหรับแนบรายงานโครงงานหรือสาธิตระบบแบบ manual ในกรณีที่ flow บางส่วนยังไม่ automate ครบ

## Public Flows

- เปิดหน้า `/` แล้ว dashboard ต้องแสดงรายการหุ้นหรือ empty state ได้โดยไม่ crash
- ค้นหาหุ้นจาก search box แล้วกดเข้า stock detail ได้
- เปิดหน้า `/stock/{ticker}` ของหุ้นที่มีข้อมูลแล้วต้องเห็นส่วน Conviction, Margin of Safety และ Quality Overview
- เปิดหน้า `/stock/UNKNOWN` แล้วต้องเห็น empty state ของ ticker ที่ไม่มีข้อมูล

## Admin Flows

- เปิดหน้า `/admin` ตอนยังไม่ล็อกอินแล้วต้องถูกพาไปหน้า `/login` หรือเห็น admin shell ตาม session ที่มีอยู่
- กดปุ่ม Google sign-in ได้เมื่อ Supabase OAuth ถูกตั้งค่าครบ
- ผู้ใช้ที่ไม่อยู่ใน `ADMIN_EMAILS` ต้องเข้า `/admin` ไม่ได้

## Publication Safety

- ตรวจว่า `.env` และ `frontend/.env.local` ไม่ถูก track ใน git
- ตรวจว่า README ใช้โดเมนตัวอย่าง ไม่ชี้ production จริง
- ตรวจว่า API keys, admin emails และ database URLs ของจริงไม่อยู่ใน source ที่จะเผยแพร่
