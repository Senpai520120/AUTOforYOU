variable "region" {
  description = "Регион AWS"
  type        = string
  default     = "eu-central-1"
}

variable "instance_type" {
  description = "Тип инстанса"
  type        = string
  default     = "m7i-flex.large"
}

variable "key_name" {
  description = "Имя существующего key pair в AWS (создавать не нужно)"
  type        = string
  default     = "autoforyou-ec2"
}

variable "root_volume_size" {
  description = "Размер root-диска, ГБ"
  type        = number
  default     = 40
}

variable "ssh_cidr" {
  description = "CIDR, с которого разрешён SSH (порт 22), например 1.2.3.4/32"
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_cidr, 0))
    error_message = "ssh_cidr должен быть корректным CIDR, например 1.2.3.4/32."
  }
}
