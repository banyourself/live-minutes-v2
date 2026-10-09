#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    exec sudo sh "$0" "$@"
fi

owner="${SUDO_USER:-ubuntu}"
export DEBIAN_FRONTEND=noninteractive

until curl -fsS -o /dev/null --max-time 10 http://ports.ubuntu.com/; do
    echo "waiting for internet access"
    sleep 10
done
while fuser /var/lib/dpkg/lock-frontend /var/lib/apt/lists/lock >/dev/null 2>&1; do
    sleep 5
done

apt-get -o DPkg::Lock::Timeout=600 update
apt-get -o DPkg::Lock::Timeout=600 -y upgrade
apt-get -o DPkg::Lock::Timeout=600 -y install docker.io docker-compose-v2 unattended-upgrades fail2ban

cat > /etc/apt/apt.conf.d/52live-minutes <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF

cat > /etc/ssh/sshd_config.d/60-live-minutes.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
MaxAuthTries 3
EOF
sshd -t
systemctl reload ssh

cat > /etc/fail2ban/jail.d/live-minutes.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
EOF
systemctl disable --now rpcbind.socket rpcbind.service 2>/dev/null || true
systemctl mask rpcbind.socket rpcbind.service 2>/dev/null || true
systemctl enable --now fail2ban docker
systemctl restart fail2ban

cat > /etc/docker/daemon.json <<'EOF'
{"log-driver": "local", "log-opts": {"max-size": "20m", "max-file": "5"}}
EOF
systemctl restart docker

usermod -aG docker "$owner"
install -d -o "$owner" -g "$owner" -m 750 /opt/live-minutes
timedatectl set-timezone America/Los_Angeles

echo "Done. Log out and back in so $owner can run docker."
