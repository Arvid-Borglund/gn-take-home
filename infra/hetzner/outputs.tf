output "server_ipv4" {
  description = "The server's public address. It goes into config/deploy.yml and .github/known_hosts."
  value       = hcloud_primary_ip.host_ipv4.ip_address
}

output "ssh" {
  description = "How to reach the server."
  value       = "ssh root@${hcloud_primary_ip.host_ipv4.ip_address}"
}
