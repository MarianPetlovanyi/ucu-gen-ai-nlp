# One droplet running the demo with Docker Compose (Caddy → Next.js → FastAPI → pipeline.py).
# DNS is not managed here: justsolution.co is on Namecheap, so the A record is added by hand (see outputs).

data "digitalocean_ssh_key" "deploy" {
  name = var.ssh_key_name
}

resource "digitalocean_droplet" "app" {
  name       = var.name
  image      = "ubuntu-24-04-x64"
  region     = var.region
  size       = var.size
  ssh_keys   = [data.digitalocean_ssh_key.deploy.id]
  monitoring = true
  user_data  = file("${path.module}/cloud-init.yaml")
  tags       = ["ucu-nlp"]
}

# A reserved IP keeps the DNS record valid if the droplet is ever replaced.
resource "digitalocean_reserved_ip" "app" {
  region = var.region
}

resource "digitalocean_reserved_ip_assignment" "app" {
  ip_address = digitalocean_reserved_ip.app.ip_address
  droplet_id = digitalocean_droplet.app.id
}

resource "digitalocean_firewall" "app" {
  name        = "${var.name}-fw"
  droplet_ids = [digitalocean_droplet.app.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.ssh_cidrs
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "digitalocean_project" "app" {
  name        = var.name
  description = "UCU GenAI Assignment 1: NDA playbook reviewer demo"
  purpose     = "Web Application"
  environment = "Production"
  resources   = [digitalocean_droplet.app.urn, digitalocean_reserved_ip.app.urn]
}
