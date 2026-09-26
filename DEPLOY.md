# نشر التطبيق على سيرفرك (Ubuntu + Nginx + DuckDNS)

هذا الدليل مخصص لسيرفر عليه بالفعل Ubuntu وNginx وDuckDNS. اتبع الخطوات بالترتيب.
كل أوامر `sudo` تُنفَّذ على السيرفر نفسه (عبر SSH)، وليس على جهازك.

## 0) قبل البدء
- تأكد أن نطاق DuckDNS الخاص بك (مثل `yourname.duckdns.org`) يشير فعليًا إلى IP هذا السيرفر
  (من لوحة duckdns.org).
- استبدل `yourname.duckdns.org` و`/var/www/newhope` في كل الأوامر أدناه بما يناسبك إن اخترت مسارًا مختلفًا.

## 1) رفع المشروع
```bash
sudo mkdir -p /var/www/newhope
sudo chown $USER:$USER /var/www/newhope
# ارفع محتويات هذا المشروع إلى /var/www/newhope عبر scp أو git أو rsync، مثال بـ rsync من جهازك:
#   rsync -avz --exclude venv --exclude db.sqlite3 ./ user@server:/var/www/newhope/
cd /var/www/newhope
```

## 2) البيئة الافتراضية والتثبيت
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip sqlite3
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3) ملف الإعدادات السرية
```bash
cp .env.example /etc/newhope.env.tmp
sudo mv /etc/newhope.env.tmp /etc/newhope.env
sudo nano /etc/newhope.env   # عدّل SECRET_KEY (سلسلة عشوائية طويلة) وALLOWED_HOSTS وCSRF_TRUSTED_ORIGINS
sudo chmod 600 /etc/newhope.env
```
لتوليد SECRET_KEY عشوائي جيد:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

## 4) قاعدة البيانات والملفات الثابتة والمستخدم الأول
```bash
set -a; source /etc/newhope.env; set +a   # تحميل المتغيرات في الجلسة الحالية للأوامر التالية
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser          # أنشئ أول حساب مدير (سيُعامَل تلقائيًا كـ"مدير كامل الصلاحيات")
```

## 5) تشغيل التطبيق بـ Gunicorn كخدمة دائمة
```bash
sudo cp deploy/newhope.service /etc/systemd/system/newhope.service
sudo nano /etc/systemd/system/newhope.service   # تأكد من المسار /var/www/newhope والمستخدم www-data مناسبين
sudo chown -R www-data:www-data /var/www/newhope
sudo systemctl daemon-reload
sudo systemctl enable --now newhope
sudo systemctl status newhope    # يجب أن تكون active (running)
```

## 6) Nginx
```bash
sudo cp deploy/nginx_newhope.conf /etc/nginx/sites-available/newhope
sudo nano /etc/nginx/sites-available/newhope   # ضع نطاقك بدل yourname.duckdns.org
sudo ln -s /etc/nginx/sites-available/newhope /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```
جرّب الآن فتح `http://yourname.duckdns.org` — يجب أن تظهر شاشة تسجيل الدخول (بدون HTTPS بعد).

## 7) HTTPS مجانًا عبر Certbot
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourname.duckdns.org
```
سيعدّل certbot ملف Nginx تلقائيًا لإضافة HTTPS والتحويل التلقائي من http. بعدها افتح
`https://yourname.duckdns.org` — رابطك النهائي هو هذا.

## 8) نسخ احتياطي تلقائي يومي
```bash
chmod +x deploy/backup.sh
crontab -e
# أضف هذا السطر:
0 2 * * * /var/www/newhope/deploy/backup.sh >> /var/log/newhope-backup.log 2>&1
```
هذا يحفظ نسخة آمنة من قاعدة البيانات يوميًا في `/var/www/newhope/backups/` ويحذف ما مضى عليه أكثر
من 30 يومًا. يمكنك أيضًا تحميل نسخة يدويًا في أي وقت من: الإعدادات ← تحميل نسخة احتياطية.

## بعد أي تحديث للكود مستقبلًا
```bash
cd /var/www/newhope
source venv/bin/activate
git pull   # أو ارفع الملفات الجديدة بنفس الطريقة السابقة
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart newhope
```

## استكشاف الأخطاء
- `sudo journalctl -u newhope -f` — سجل أخطاء Gunicorn/Django مباشرة.
- `sudo nginx -t` — يتحقق من صحة إعدادات Nginx قبل تطبيقها.
- تأكد أن `/etc/newhope.env` قابل للقراءة من `www-data` فقط (`chmod 600` + المالك صحيح لو احتجت
  `sudo chown root:www-data /etc/newhope.env`).
