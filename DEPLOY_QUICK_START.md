# 🚀 Deploy Rapido su Linode - Guida Passo-Passo

**Versione**: 2.1
**Data**: 2025-10-10
**Tempo stimato**: 30-45 minuti

---

## 📋 Prima di Iniziare

### Hai Bisogno Di:
1. ✅ Account Linode attivo
2. ✅ VPS Linode (minimo 1GB RAM - $5/mese)
3. ✅ Tutti i file del progetto sul tuo PC
4. ✅ File `.env` con tutte le credenziali
5. ✅ File `fresh-electron-318314-*.json` (Service Account Google)
6. ✅ File `telegram_session.session` (se esiste)

---

## 🎯 Deploy in 5 Step

### STEP 1: Preparare il Server (10 min)

```bash
# SSH al server
ssh root@your-linode-ip

# Update sistema
apt update && apt upgrade -y

# Installa dipendenze
apt install -y python3 python3-pip python3-venv git sqlite3 nginx

# Crea utente dedicato
adduser --disabled-password --gecos "" lezioni-russo
usermod -aG sudo lezioni-russo

# Passa all'utente
su - lezioni-russo
```

---

### STEP 2: Upload Progetto (5 min)

**Opzione A: Upload da PC locale**

Sul tuo PC (apri nuovo terminale):
```bash
# Vai nella directory del progetto
cd /home/arjuna/nextcloud

# Upload tramite rsync
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='pagamenti.db' --exclude='*.log' \
  ./ lezioni-russo@your-linode-ip:~/lezioni-russo/
```

**Opzione B: Da Git** (se hai repo)
```bash
cd ~
git clone <your-repo-url> lezioni-russo
cd lezioni-russo
```

---

### STEP 3: Setup Python e Dipendenze (5 min)

Sul server:
```bash
cd ~/lezioni-russo

# Crea virtual environment
python3 -m venv .cal

# Attiva venv
source .cal/bin/activate

# Installa dipendenze
pip install --upgrade pip
pip install flask python-telegram-bot telethon python-dotenv \
  google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

---

### STEP 4: Configurazione File e Test (10 min)

```bash
# Verifica file .env esiste
cat .env

# Se manca, crealo:
nano .env
```

**Contenuto `.env`:**
```bash
# Telegram Bot
BOT_TOKEN=7762615672:AAFK0-ZcJIN2f27ePQaxhsL-kfwZqaFWsJo

# Telegram User API
API_ID=21581367
API_HASH=96c0f7df64d4422476f6a988f5dae600
PHONE_NUMBER=+79168231142
TELEGRAM_PASSWORD=j9099Wjkio
CHANNEL_ID=-1002452167729

# Google Calendar
GCAL_CALENDAR_ID=5e7ecd0336fee20b4ae7b132634044396c0babf455b22c35cbde6986392cccb1@group.calendar.google.com
GCAL_SERVICE_ACCOUNT_FILE=fresh-electron-318314-050d19bd162e.json

# Admin (trova il tuo con @userinfobot su Telegram)
ADMIN_CHAT_ID=<your-telegram-user-id>
```

**Upload Service Account JSON** (se non già fatto):
```bash
# Sul tuo PC:
scp fresh-electron-318314-050d19bd162e.json \
  lezioni-russo@your-linode-ip:~/lezioni-russo/
```

**Inizializza DB** (se non esiste):
```bash
.cal/bin/python db_create_schema.py
```

**Test veloce:**
```bash
# Test bot (Ctrl+C per uscire dopo 5 secondi)
.cal/bin/python association_resolver.py
# Se vedi "Bot avviato!" → OK ✅

# Test web interface (Ctrl+C per uscire)
cd web_interface
../.cal/bin/python app.py
# Se vedi "Running on http://127.0.0.1:5000" → OK ✅
```

---

### STEP 5: Automazione Produzione (10-15 min)

#### A) Bot Telegram come Servizio

```bash
sudo nano /etc/systemd/system/lezioni-russo-bot.service
```

**Contenuto:**
```ini
[Unit]
Description=Lezioni Russo Telegram Bot
After=network.target

[Service]
Type=simple
User=lezioni-russo
WorkingDirectory=/home/lezioni-russo/lezioni-russo
Environment="PATH=/home/lezioni-russo/lezioni-russo/.cal/bin"
ExecStart=/home/lezioni-russo/lezioni-russo/.cal/bin/python association_resolver.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Avvia bot:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable lezioni-russo-bot
sudo systemctl start lezioni-russo-bot
sudo systemctl status lezioni-russo-bot
```

#### B) Web Interface come Servizio

**Modifica app.py per produzione:**
```bash
nano ~/lezioni-russo/web_interface/app.py
```

Cambia ultima riga da:
```python
app.run(debug=True, host='0.0.0.0', port=5000)
```

a:
```python
app.run(debug=False, host='127.0.0.1', port=5000)
```

**Crea servizio:**
```bash
sudo nano /etc/systemd/system/lezioni-russo-web.service
```

**Contenuto:**
```ini
[Unit]
Description=Lezioni Russo Web Interface
After=network.target

[Service]
Type=simple
User=lezioni-russo
WorkingDirectory=/home/lezioni-russo/lezioni-russo/web_interface
Environment="PATH=/home/lezioni-russo/lezioni-russo/.cal/bin"
ExecStart=/home/lezioni-russo/lezioni-russo/.cal/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Avvia web:**
```bash
sudo systemctl enable lezioni-russo-web
sudo systemctl start lezioni-russo-web
sudo systemctl status lezioni-russo-web
```

#### C) Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/lezioni-russo
```

**Contenuto:**
```nginx
server {
    listen 80;
    server_name your-linode-ip;  # O tuo dominio

    access_log /var/log/nginx/lezioni-russo-access.log;
    error_log /var/log/nginx/lezioni-russo-error.log;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    # Autenticazione HTTP (opzionale ma consigliato)
    auth_basic "Lezioni Russo Admin";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```

**Crea password:**
```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
# Inserisci password quando richiesto
```

**Attiva:**
```bash
sudo ln -s /etc/nginx/sites-available/lezioni-russo /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### D) Cron Job Sync Automatico

```bash
crontab -e
```

**Aggiungi:**
```bash
# Sync automatico ogni ora (al minuto 05)
5 * * * * cd /home/lezioni-russo/lezioni-russo && .cal/bin/python telegram_ingestor.py >> logs/cron_telegram.log 2>&1
10 * * * * cd /home/lezioni-russo/lezioni-russo && .cal/bin/python -c "from association_resolver import sync_lessons_from_calendar; sync_lessons_from_calendar()" >> logs/cron_gcal.log 2>&1

# Backup database giornaliero (alle 3:00)
0 3 * * * mkdir -p /home/lezioni-russo/lezioni-russo/backups && cp /home/lezioni-russo/lezioni-russo/pagamenti.db /home/lezioni-russo/lezioni-russo/backups/pagamenti_$(date +\%Y\%m\%d).db

# Pulizia backup vecchi (mantieni 30 giorni)
0 4 * * * find /home/lezioni-russo/lezioni-russo/backups/ -name "pagamenti_*.db" -mtime +30 -delete
```

**Crea directory logs:**
```bash
mkdir -p ~/lezioni-russo/logs
mkdir -p ~/lezioni-russo/backups
```

---

## 🔒 Sicurezza (Opzionale ma Consigliato)

```bash
# Firewall
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable

# Fail2ban
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Permessi file
cd ~/lezioni-russo
chmod 600 .env
chmod 600 *.json
chmod 600 *.session
chmod 644 pagamenti.db
```

---

## ✅ Verifica Finale

```bash
# 1. Verifica bot è attivo
sudo systemctl status lezioni-russo-bot
# Deve dire "active (running)"

# 2. Verifica web è attivo
sudo systemctl status lezioni-russo-web
# Deve dire "active (running)"

# 3. Verifica nginx
sudo systemctl status nginx
# Deve dire "active (running)"

# 4. Test web interface
# Apri browser: http://your-linode-ip
# Dovrebbe chiedere username/password (admin / <tua-password>)
# Poi mostrare l'interfaccia web

# 5. Test bot Telegram
# Apri Telegram, cerca il tuo bot
# Invia: /start
# Dovrebbe rispondere con menu comandi

# 6. Test sync automatico
# Aspetta 5 minuti dopo l'ora (es. 15:05)
# Controlla log:
tail -f ~/lezioni-russo/logs/cron_telegram.log
tail -f ~/lezioni-russo/logs/cron_gcal.log
```

---

## 📊 Monitoraggio

```bash
# Log bot
sudo journalctl -u lezioni-russo-bot -f

# Log web
sudo journalctl -u lezioni-russo-web -f

# Log nginx
sudo tail -f /var/log/nginx/lezioni-russo-access.log
sudo tail -f /var/log/nginx/lezioni-russo-error.log

# Log cron
tail -f ~/lezioni-russo/logs/cron_telegram.log
tail -f ~/lezioni-russo/logs/cron_gcal.log

# Log bot applicativo
tail -f ~/lezioni-russo/association_resolver.log
```

---

## 🔄 Comandi Utili

```bash
# Restart servizi
sudo systemctl restart lezioni-russo-bot
sudo systemctl restart lezioni-russo-web
sudo systemctl reload nginx

# Stop servizi
sudo systemctl stop lezioni-russo-bot
sudo systemctl stop lezioni-russo-web

# View logs in tempo reale
sudo journalctl -u lezioni-russo-bot -f
sudo journalctl -u lezioni-russo-web -f

# Verifica DB
sqlite3 ~/lezioni-russo/pagamenti.db "SELECT COUNT(*) FROM pagamenti;"
sqlite3 ~/lezioni-russo/pagamenti.db "SELECT COUNT(*) FROM lezioni;"

# Update codice
cd ~/lezioni-russo
git pull  # se usi git
# Oppure:
# rsync dal PC locale
sudo systemctl restart lezioni-russo-bot
sudo systemctl restart lezioni-russo-web
```

---

## 🆘 Troubleshooting

### Bot non si avvia
```bash
# Controlla log
sudo journalctl -u lezioni-russo-bot -n 50

# Verifica file .env
cat ~/lezioni-russo/.env

# Test manuale
cd ~/lezioni-russo
source .cal/bin/activate
python association_resolver.py
```

### Web interface non accessibile
```bash
# Verifica servizio
sudo systemctl status lezioni-russo-web

# Verifica nginx
sudo nginx -t
sudo systemctl status nginx

# Test locale
curl http://127.0.0.1:5000
```

### Cron non funziona
```bash
# Verifica crontab
crontab -l

# Verifica log
tail -f ~/lezioni-russo/logs/cron_telegram.log

# Test manuale
cd ~/lezioni-russo
.cal/bin/python telegram_ingestor.py
```

---

## 📞 Comandi Telegram Bot

Una volta attivo, usa questi comandi sul bot:

- `/start` - Menu comandi
- `/process` - Processa pagamenti di OGGI (sync automatico lezioni)
- `/suspended` - Riprocessa pagamenti saltati
- `/sync` - Sincronizza lezioni da Google Calendar (ultimi 60 giorni)

**Ricorda**: Il bot mostra SOLO pagamenti e lezioni di OGGI. Per storico usa web interface.

---

## 🎯 Checklist Finale

- [ ] Bot Telegram attivo e risponde a `/start`
- [ ] Web interface accessibile su browser (http://your-ip)
- [ ] Autenticazione HTTP funzionante (username/password)
- [ ] Cron job configurati (verifica tra 1 ora)
- [ ] Backup automatico configurato (verifica domani alle 3:00)
- [ ] Firewall attivo
- [ ] Fail2ban installato
- [ ] Permessi file corretti (600 per .env e .json)

---

## 🚀 Sistema Pronto!

**Accedi a:**
- Web Interface: `http://your-linode-ip` (username: admin, password: <tua-password>)
- Bot Telegram: Cerca il tuo bot su Telegram e invia `/start`

**Workflow Quotidiano:**
1. Ogni ora (HH:05) → Sync automatico pagamenti e lezioni
2. Ogni giorno → Bot su Telegram per associazioni immediate (SOLO OGGI)
3. Quando serve → Web interface per storico e abbinamenti complessi

**Backup:**
- Database backup automatico ogni giorno alle 3:00 AM
- Retention: 30 giorni
- Posizione: `~/lezioni-russo/backups/`

---

**Tempo totale deployment: ~30-45 minuti** ✅

**Costo: $5/mese (Linode Nanode 1GB)** 💰

**Pronto per produzione!** 🎉
