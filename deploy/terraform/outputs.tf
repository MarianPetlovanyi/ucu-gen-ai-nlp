output "ip" {
  description = "Reserved IP: point the DNS A record here"
  value       = digitalocean_reserved_ip.app.ip_address
}

output "dns_record" {
  description = "Record to add at Namecheap (Advanced DNS) for justsolution.co"
  value       = "A  ${trimsuffix(var.domain, ".justsolution.co")}  ${digitalocean_reserved_ip.app.ip_address}"
}

output "url" {
  value = "https://${var.domain}"
}

output "ssh" {
  value = "ssh -i ~/.ssh/mlops_do root@${digitalocean_reserved_ip.app.ip_address}"
}
