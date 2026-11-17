# Terraform: временный сервер AUTOforYOU (AWS EC2)

## Что создаётся
- EC2 `m7i-flex.large`, Ubuntu 24.04 (свежий AMI Canonical), root gp3 40 ГБ, шифрование, IMDSv2.
- Security group `autoforyou-web-tf` (VPC по умолчанию): 80/443 отовсюду, 22 только с `ssh_cidr`.
- Elastic IP, привязанный к инстансу.
- Key pair `autoforyou-ec2` должен уже существовать в AWS (Terraform его не создаёт).
- Docker, деплой и секреты в Terraform не входят (никакого user_data).

## Команды
```
cd infra/terraform
copy terraform.tfvars.example terraform.tfvars   # впишите свой ssh_cidr
terraform init
terraform plan
terraform apply
terraform destroy
```
Свой IP: `curl https://checkip.amazonaws.com` (в tfvars — `1.2.3.4/32`).

## State
State локальный (`terraform.tfstate`), в git не попадает. В нём только IP и id, потерять не страшно,
но без него `destroy` придётся делать руками в консоли/CLI. `.terraform.lock.hcl` коммитится.

## После apply
Идти по `docs/DEPLOY_EC2_CHECKLIST.md`. `.env` лежит в `C:\Users\kirit\.ssh\autoforyou-ec2.env`:
поправьте в нём `DOMAIN`, `SITE_URL`, `ALLOWED_HOSTS` под новый адрес из output `sslip_domain`.
После `destroy` и нового `apply` IP будет другим, значит, и sslip-домен тоже.
