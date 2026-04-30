# Cloud Harvest Runbook — Oracle Cloud Always Free

**Formål:** Kjøre sub-fase 12.6-harvest på cloud i stedet for å stresse gammel laptop i 24t.

**Valgt leverandør:** Oracle Cloud Always Free Tier.
- 4 vCPU ARM Ampere A1 + 24GB RAM
- ALDRI utløp (ikke 30/90-dagers trial)
- 200GB block storage inkludert
- Krever kredittkort for ID-verifisering, ALDRI charge på Always Free
- Sammenlignbar ytelse med laptop (samme 4-core parallell-modus)

## Steg 1 — Sign up Oracle Cloud (~10 min)

1. Gå til https://signup.cloud.oracle.com
2. Velg "Always Free" / "Free Tier"
3. Fyll inn:
   - E-post + passord
   - Land: Norway
   - Telefon (SMS-verifisering)
   - Kredittkort (for verifisering — ALDRI belastet på Always Free)
   - Hjemmeregion: **Frankfurt** eller **Stockholm** (lavest latency fra Norge)

4. Vent ~5 min på account-approval. Du får en e-post når klar.

## Steg 2 — Provisionere ARM-instance (~10 min)

I Oracle Cloud Console:

1. Naviger til **Menu → Compute → Instances**
2. Klikk **Create Instance**
3. Konfigurer:
   - **Name:** `bedrock-harvest`
   - **Image:** `Canonical Ubuntu 24.04` (ARM-versjonen)
   - **Shape:** klikk "Change shape"
     - Series: **Ampere**
     - Shape: **VM.Standard.A1.Flex**
     - OCPUs: **4**
     - RAM: **24 GB**
   - **Networking:** Standard, default VCN
   - **SSH-keys:** klikk "Generate a key pair for me", last ned **private key** (ssh-key.key)
4. Klikk **Create**

> ⚠️ **Hvis du får "Out of host capacity"-feil:** ARM-instances er etterspurt. Prøv:
> - Annen region (Stockholm/Amsterdam/London)
> - Vent 15 min, prøv igjen
> - Bruk x86 AMD-instance (VM.Standard.E2.1.Micro × 2 — 2 vCPU/2GB hver, mindre kraft men også Always Free)

5. Vent ~3 min til instance status = **RUNNING**
6. Noter **Public IPv4 Address** (vises i instance-oversikten)

## Steg 3 — Konfigurer SSH (~5 min)

På din lokale laptop:

```bash
# Lagre nedlastet private key
chmod 600 ~/Downloads/ssh-key.key
mv ~/Downloads/ssh-key.key ~/.ssh/oracle_bedrock.pem

# Test SSH-forbindelse (erstatt <IP> med public IP fra Oracle)
ssh -i ~/.ssh/oracle_bedrock.pem ubuntu@<IP>

# Du skal nå være innlogget som ubuntu@bedrock-harvest
```

Hvis SSH henger:
- Sjekk Oracle Cloud → Networking → VCN → Security List → tilatte ingress-regler skal inkludere TCP/22 fra 0.0.0.0/0

## Steg 4 — Installere dependencies på VM (~10 min)

På cloud-VM (etter SSH-innlogging):

```bash
# Oppdater + install
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git sqlite3 build-essential

# Opprett bedrock-mappe
mkdir -p ~/bedrock && cd ~/bedrock

# Klon repo (public eller med deploy-key)
git clone https://github.com/<din-bruker>/bedrock.git .
# eller kopier via scp fra laptop hvis privat repo:
# (kjøres på LAPTOP)
# rsync -avz --exclude='.venv' --exclude='data/bedrock.db' \
#   /home/pc/bedrock/ ubuntu@<IP>:~/bedrock/

# Sett opp virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# Installere uv eller pip-install requirements
pip install --upgrade pip
pip install -e .  # antagelse: pyproject.toml definerer dependencies
# Hvis ikke pyproject-installerbart, bruk eksplisitt requirements:
# pip install pandas numpy sqlite3 structlog tenacity pydantic pyyaml ruff
```

## Steg 5 — Overføre bedrock.db (~3 min)

Bedrock.db er 82MB med all historikk. Overfør én gang.

På laptop (kjør):

```bash
# Komprimer + send
cd /home/pc/bedrock/data
sqlite3 bedrock.db ".backup bedrock.db.snapshot"  # consistent snapshot
gzip -k bedrock.db.snapshot  # ca. 30-40MB komprimert
scp -i ~/.ssh/oracle_bedrock.pem bedrock.db.snapshot.gz \
    ubuntu@<IP>:~/bedrock/data/bedrock.db.gz
rm bedrock.db.snapshot bedrock.db.snapshot.gz
```

På cloud-VM:

```bash
cd ~/bedrock/data
gunzip bedrock.db.gz
ls -la bedrock.db   # skal være 82MB

# Verifiser DB
sqlite3 bedrock.db "SELECT COUNT(*) FROM driver_observations"
# Forventet: ~39,888 rader (current state ved overføring)

# Sett WAL-mode for å fortsette parallel harvest
sqlite3 bedrock.db "PRAGMA journal_mode=WAL"
```

## Steg 6 — Start harvest på cloud (~1 min)

På cloud-VM:

```bash
cd ~/bedrock
source .venv/bin/activate

# Start parallel harvest (uten nice/ionice — VM-en er din alene)
nohup ./scripts/run_parallel_harvest.sh > data/_meta/harvest_cloud.log 2>&1 &
echo $! > data/_meta/harvest_cloud.pid

# Verifiser
sleep 10
ps -p $(cat data/_meta/harvest_cloud.pid)
tail -20 data/_meta/harvest_cloud.log
```

> Ingen fetch-timere på VM (vi pauser dem ikke fordi de ikke finnes der). Dropp
> `BEDROCK_HARVEST_RESUME_TIMERS` (default 1, men `systemctl --user start` vil
> da feile 10 ganger med exit-status — irrelevant, harvest fortsetter).
> Eller skru av eksplisitt:
>
> ```bash
> BEDROCK_HARVEST_RESUME_TIMERS=0 nohup ./scripts/run_parallel_harvest.sh ...
> ```

## Steg 7 — Lukk SSH, la cloud-VM kjøre (~24t)

```bash
# Lukk SSH-økten — harvest kjører videre
exit
```

Cloud-VM-en kjører selvstendig. Sjekk progresjon når som helst:

```bash
ssh -i ~/.ssh/oracle_bedrock.pem ubuntu@<IP> \
  "sqlite3 ~/bedrock/data/bedrock.db 'SELECT instrument, COUNT(*) FROM driver_observations GROUP BY instrument ORDER BY 1'"
```

## Steg 8 — Hente resultater når ferdig (~3 min)

På laptop:

```bash
# Sjekk om ferdig
ssh -i ~/.ssh/oracle_bedrock.pem ubuntu@<IP> \
  "pgrep -af run_parallel_harvest || echo DONE"
# Hvis "DONE" → harvest fullført

# Hent oppdatert DB
cd /home/pc/bedrock/data
mv bedrock.db bedrock.db.before-cloud-backup

ssh -i ~/.ssh/oracle_bedrock.pem ubuntu@<IP> \
  "cd ~/bedrock/data && sqlite3 bedrock.db '.backup bedrock.db.final' && gzip bedrock.db.final"
scp -i ~/.ssh/oracle_bedrock.pem ubuntu@<IP>:~/bedrock/data/bedrock.db.final.gz .
gunzip bedrock.db.final.gz
mv bedrock.db.final bedrock.db

# Verifiser
sqlite3 bedrock.db "SELECT instrument, COUNT(*) FROM driver_observations GROUP BY instrument ORDER BY 1"
```

## Steg 9 — Slette VM (sparer Oracle-quota)

Når DB er overført tilbake og verifisert:

I Oracle Cloud Console:
1. Compute → Instances → klikk `bedrock-harvest`
2. **Stop** instance (sparer state, ingen kostnad uansett)
3. Eller **Terminate** for full sletting

> Always Free har 2 ARM-instances som quota. Det er greit å beholde VM-en hvis
> du planlegger flere kjøringer (analyzer-runde, fremtidig re-harvest).
> Bare stopp den når den ikke brukes.

## Backup-plan: Hvis Oracle Cloud ikke fungerer

**GitHub Codespaces** (60h/måned gratis, ingen kredittkort):

```bash
# Lokalt: push eventuelle uncommittede changes
cd /home/pc/bedrock && git push

# I nettleser: github.com → bedrock-repo → Code → Codespaces → Create on main
# Velg "4-core 16GB" som machine type
# Vent 2-3 min på provisioning

# I Codespace-terminal:
pip install -e .
# scp DB fra laptop (krever offentlig endepunkt på laptop, eller bruk transfer.sh)

# Caveat: Codespaces auto-suspender etter 30 min idle.
# Workaround: Hold VS Code-fanen åpen, eller bruk:
# while true; do echo keepalive; sleep 300; done &
```

## Forventet kostnad

| Tjeneste | Kostnad |
|---|---|
| Oracle Cloud Always Free ARM-VM | **0 kr** |
| Egress traffic (sende DB tilbake, ~200MB) | **0 kr** (10TB/mnd gratis) |
| Storage (200GB inkludert) | **0 kr** |
| **Total** | **0 kr** |

## Når du er klar

Si fra her i Claude Code når:

1. ✅ **VM er provisionert** — gi meg public IP-en så veileder jeg overføring
2. ✅ **SSH fungerer** — vi går til Steg 4
3. ✅ **Harvest restartet på cloud** — vi venter på completion
4. ✅ **Harvest ferdig** — vi henter DB tilbake og kjører analyzer

Om du støter på problemer underveis (signup-feil, ARM out-of-capacity, SSH-trøbbel),
kopier feilmelding hit så foreslår jeg en fix.
