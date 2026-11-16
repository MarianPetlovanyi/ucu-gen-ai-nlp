variable "do_token" {
  description = "DigitalOcean API token. Pass it as TF_VAR_do_token; never commit it."
  type        = string
  sensitive   = true
}

variable "name" {
  description = "Name of the droplet, firewall and DO project"
  type        = string
  default     = "ucu-nlp-nda-review"
}

variable "region" {
  description = "DigitalOcean region (fra1 had no droplet sizes available on 2026-11-16, so lon1)"
  type        = string
  default     = "lon1"
}

variable "size" {
  description = "Droplet size. 4 GB RAM covers torch (CPU), bge-small, Next.js and the Docker builds."
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "ssh_key_name" {
  description = "Name of an SSH key already uploaded to the DO account (its private half is used by deploy.sh)"
  type        = string
  default     = "mlops-digitalocean"
}

variable "domain" {
  description = "Public host name. DNS is managed outside DO (Namecheap): add an A record for it to the reserved IP."
  type        = string
  default     = "ucu.nlp.justsolution.co"
}

variable "ssh_cidrs" {
  description = "Addresses allowed to reach SSH. Narrow to <your-ip>/32 if you like; auth is key-only either way."
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}
