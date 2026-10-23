#!/bin/bash
# ==============================================================================
# NexAgent AWS EC2 One-Time Setup Script (Free Tier Optimized)
# ==============================================================================
set -e

echo "=========================================================="
echo "⚡ Starting NexAgent EC2 Environment Configuration..."
echo "=========================================================="

# 1. Update OS Packages
echo "🔄 Updating apt packages..."
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y git curl wget ca-certificates gnupg lsb-release

# 2. Setup 4GB Swap Space (Crucial for t2.micro 1GB RAM)
echo "💾 Configuring 4GB Swap memory to prevent Out-Of-Memory crashes..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 4G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "vm.swappiness=20" | sudo tee -a /etc/sysctl.conf
    echo "vm.vfs_cache_pressure=50" | sudo tee -a /etc/sysctl.conf
    sudo sysctl -p
    echo "✅ 4GB Swap created successfully!"
else
    echo "ℹ️ Swapfile already exists."
fi

# 3. Install Official Docker & Docker Compose
echo "🐳 Installing Docker Engine and Docker Compose plugin..."
if ! command -v docker &> /dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Enable docker service
    sudo systemctl enable docker
    sudo systemctl start docker

    # Add current user to docker group
    sudo usermod -aG docker "$USER"
    echo "✅ Docker installed successfully!"
else
    echo "ℹ️ Docker is already installed."
fi

echo "=========================================================="
echo "🎉 Server Setup Complete!"
echo "Please run: 'newgrp docker' or log out and log back in."
echo "=========================================================="
