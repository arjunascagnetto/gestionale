# 🚀 Deployment su Linode VPS

## 📋 Prerequisiti

- VPS Linode attivo (Ubuntu 22.04 o 24.04)
- SSH access
- Minimo 1GB RAM, 1 vCPU

---

## 🔧 Setup Iniziale

### 1. Connessione SSH e Update Sistema

```bash
ssh root@your-linode-ip

# Update sistema
apt update && apt upgrade -y

# Installa dipendenze base
apt install -y python3 python3-pip python3-venv git sqlite3 nginx
```

### 2. Crea Utente Applicazione (sicurezza)

```bash
# Crea utente dedicato
adduser --disabled-password --gecos "" lezioni-russo
usermod -aG sudo lezioni-russo

# Passa all'utente
su - lezioni-russo
```

### 3. Clona/Upload Progetto

**Opzione A: Da Git** (se hai repository)
```bash
cd ~
git clone <your-repo-url> lezioni-russo
cd lezioni-russo
```

**Opzione B: Upload Manuale**
```bash
# Sul tuo PC locale:
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  /home/arjuna/nextcloud/ lezioni-russo@your-linode-ip:~/lezioni-russo/
```

### 4. Setup Python Virtual Environment

```bash
cd ~/lezioni-russo

# Crea venv
python3 -m venv .cal

# Attiva venv
source .cal/bin/activate

# Installa dipendenze
pip install --upgrade pip
pip install flask python-telegram-bot telethon python-dotenv \
  google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 5. Configura File .env

```bash
nano .env
```

Inserisci tutte le credenziali:
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
```

### 6. Upload Credenziali Google

```bash
# Sul tuo PC locale:
scp fresh-electron-318314-050d19bd162e.json \
  lezioni-russo@your-linode-ip:~/lezioni-russo/
```

### 7. Inizializza Database (se non esiste)

```bash
cd ~/lezioni-russo
.cal/bin/python db_create_schema.py
```

---

## ⏰ Automazione con Cron Jobs

### Strategia di Esecuzione Automatica

```
┌──────────────────────────────────────────────┐
│ SCHEDULE AUTOMATICO                          │
└──────────────────────────────────────────────┘

Ogni ora (00 minuti):
  → Scarica nuovi pagamenti da Telegram
  → Sincronizza nuove lezioni da Google Calendar
  → Aggiorna Google Calendar (incrementale)

Comando manuale via bot:
  → /process - Abbina pagamenti interattivamente
```

### Script Wrapper per Cron

Crea uno script che esegue tutto in sequenza:

```bash
nano ~/lezioni-russo/cron_hourly_sync.sh
```

**Contenuto:**
```bash
#!/bin/bash
# Script eseguito ogni ora da cron per sincronizzare dati

# Directory progetto
PROJECT_DIR="/home/lezioni-russo/lezioni-russo"
cd "$PROJECT_DIR"

# Attiva virtual environment
source .cal/bin/activate

# Log file
LOG_FILE="$PROJECT_DIR/logs/cron_sync.log"
mkdir -p "$(dirname "$LOG_FILE")"

echo "=========================================" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - Sync automatico avviato" >> "$LOG_FILE"

# 1. Scarica nuovi pagamenti da Telegram (ultimi messaggi)
echo "📥 Scaricamento pagamenti..." >> "$LOG_FILE"
python3 telegram_ingestor.py >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Pagamenti scaricati" >> "$LOG_FILE"
else
    echo "❌ Errore scaricamento pagamenti" >> "$LOG_FILE"
fi

# 2. Sincronizza nuove lezioni da Google Calendar
echo "📅 Sincronizzazione lezioni..." >> "$LOG_FILE"
python3 gcal_bulk_sync.py >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Lezioni sincronizzate" >> "$LOG_FILE"
else
    echo "❌ Errore sincronizzazione lezioni" >> "$LOG_FILE"
fi

# 3. Aggiorna Google Calendar (solo modifiche incrementali)
echo "🔄 Aggiornamento Google Calendar..." >> "$LOG_FILE"
python3 update_gcal_incremental.py >> "$LOG_FILE" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Calendar aggiornato" >> "$LOG_FILE"
else
    echo "❌ Errore aggiornamento calendar" >> "$LOG_FILE"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Sync completato" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
```

**Rendi eseguibile:**
```bash
chmod +x ~/lezioni-russo/cron_hourly_sync.sh
```

### Configurazione Crontab

```bash
crontab -e
```

**Aggiungi questa linea:**
```bash
# Sync automatico ogni ora (al minuto 05)
5 * * * * /home/lezioni-russo/lezioni-russo/cron_hourly_sync.sh

# Backup database giornaliero (alle 3:00)
0 3 * * * cp /home/lezioni-russo/lezioni-russo/pagamenti.db \
  /home/lezioni-russo/lezioni-russo/backups/pagamenti_$(date +\%Y\%m\%d).db

# Pulizia backup vecchi (mantieni ultimi 30 giorni)
0 4 * * * find /home/lezioni-russo/lezioni-russo/backups/ -name "pagamenti_*.db" -mtime +30 -delete
```

**Spiegazione cron syntax:**
```
┌───────────── minuto (0 - 59)
│ ┌───────────── ora (0 - 23)
│ │ ┌───────────── giorno del mese (1 - 31)
│ │ │ ┌───────────── mese (1 - 12)
│ │ │ │ ┌───────────── giorno della settimana (0 - 6, 0=domenica)
│ │ │ │ │
5 * * * *   → Ogni ora al minuto 5 (00:05, 01:05, 02:05, ...)
```

### Test Manuale Script

```bash
# Esegui manualmente per testare
cd ~/lezioni-russo
./cron_hourly_sync.sh

# Controlla log
tail -f logs/cron_sync.log
```

---

## 🌐 Setup Interfaccia Web con Nginx

### 1. Configurazione Flask come Servizio Systemd

Crea service file:
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

**Avvia servizio:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable lezioni-russo-web
sudo systemctl start lezioni-russo-web
sudo systemctl status lezioni-russo-web
```

### 2. Configurazione Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/lezioni-russo
```

**Contenuto:**
```nginx
server {
    listen 80;
    server_name your-domain.com;  # O usa IP diretto

    # Logs
    access_log /var/log/nginx/lezioni-russo-access.log;
    error_log /var/log/nginx/lezioni-russo-error.log;

    # Proxy verso Flask
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout per operazioni lunghe (sync calendar)
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
    }

    # Autenticazione HTTP Basic (opzionale ma consigliato)
    auth_basic "Lezioni Russo Admin";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```

**Crea password per autenticazione:**
```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
# Inserisci password quando richiesto
```

**Attiva configurazione:**
```bash
sudo ln -s /etc/nginx/sites-available/lezioni-russo /etc/nginx/sites-enabled/
sudo nginx -t  # Test configurazione
sudo systemctl reload nginx
```

### 3. (Opzionale) Setup SSL con Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 🤖 Bot Telegram Interattivo (association_resolver.py)

### Opzione A: Esecuzione Manuale

Quando vuoi processare pagamenti interattivamente:
```bash
ssh lezioni-russo@your-linode-ip
cd ~/lezioni-russo
source .cal/bin/activate
python association_resolver.py
```

Poi su Telegram usi `/process`, `/suspended`, `/sync`

### Opzione B: Bot come Servizio (sempre attivo)

Crea service:
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

**Avvia:**
```bash
sudo systemctl enable lezioni-russo-bot
sudo systemctl start lezioni-russo-bot
sudo systemctl status lezioni-russo-bot
```

---

## 📊 Monitoring e Logs

### Controllare Logs Cron

```bash
# Log sync automatico
tail -f ~/lezioni-russo/logs/cron_sync.log

# Log sistema cron
grep CRON /var/log/syslog
```

### Controllare Status Servizi

```bash
sudo systemctl status lezioni-russo-web
sudo systemctl status lezioni-russo-bot
sudo systemctl status nginx
```

### Log Web Interface

```bash
sudo journalctl -u lezioni-russo-web -f
```

### Log Bot Telegram

```bash
sudo journalctl -u lezioni-russo-bot -f
```

---

## 🔒 Sicurezza

### 1. Firewall (UFW)

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 2. Fail2ban (protezione SSH)

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 3. Permessi File

```bash
cd ~/lezioni-russo
chmod 600 .env
chmod 600 *.json
chmod 600 *.session
chmod 644 pagamenti.db
```

---

## 📈 Manutenzione

### Backup Automatico Database

Già configurato nel crontab:
- Backup giornaliero alle 3:00
- Retention: 30 giorni

### Update Codice

```bash
cd ~/lezioni-russo
git pull  # se usi git

# O ri-sync da PC locale:
# rsync -avz /home/arjuna/nextcloud/ lezioni-russo@ip:~/lezioni-russo/

sudo systemctl restart lezioni-russo-web
sudo systemctl restart lezioni-russo-bot
```

### Monitorare Spazio Disco

```bash
df -h
du -sh ~/lezioni-russo/*
```

---

## 🎯 Riepilogo Automazione

**Cosa succede automaticamente:**
1. ⏰ **Ogni ora (HH:05):**
   - Scarica nuovi pagamenti da Telegram
   - Sincronizza nuove lezioni da Google Calendar
   - Aggiorna colori/nomi in Google Calendar (solo modifiche)

2. 🌐 **Web Interface (sempre attiva):**
   - Accessibile su http://your-ip o https://your-domain.com
   - Protetta da username/password
   - Puoi fare abbinamenti manuali, gestire associazioni, normalizzare nomi

3. 🤖 **Bot Telegram (sempre attivo):**
   - Rispondono ai comandi `/process`, `/suspended`, `/sync`
   - Per abbinamenti interattivi quando serve

4. 💾 **Backup (giornaliero 03:00):**
   - Database salvato automaticamente
   - Retention 30 giorni

---

## 💰 Costi

**Linode VPS (Nanode 1GB):** $5/mese
- 1 vCPU
- 1GB RAM
- 25GB Storage
- 1TB Transfer

**Totale: $5/mese** (o anche meno se hai già la VM)

---

## 🚀 Quick Start Commands

```bash
# Setup completo in una volta
curl -s https://your-script-url/setup.sh | bash

# O manualmente:
ssh root@your-linode-ip
# ... segui i passaggi sopra
```

Vuoi che ti prepari uno **script di setup automatico** che fa tutto questo in un comando?
