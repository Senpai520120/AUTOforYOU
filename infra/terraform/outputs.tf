output "public_ip" {
  description = "Публичный Elastic IP сервера"
  value       = aws_eip.server.public_ip
}

output "sslip_domain" {
  description = "Домен sslip.io для этого IP"
  value       = "${replace(aws_eip.server.public_ip, ".", "-")}.sslip.io"
}

output "ssh_command" {
  description = "Команда SSH-подключения (PowerShell)"
  value       = "C:\\Windows\\System32\\OpenSSH\\ssh.exe -i $env:USERPROFILE\\.ssh\\autoforyou-ec2.pem ubuntu@${aws_eip.server.public_ip}"
}

output "instance_id" {
  description = "ID инстанса"
  value       = aws_instance.server.id
}
