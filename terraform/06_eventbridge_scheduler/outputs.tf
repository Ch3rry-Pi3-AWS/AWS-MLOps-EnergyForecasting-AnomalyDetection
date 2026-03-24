# Surface the schedule and execution role identifiers so later monitoring or
# orchestration modules can reuse them without guessing names.
output "schedule_name" {
  value = aws_scheduler_schedule.main.name
}

output "schedule_arn" {
  value = aws_scheduler_schedule.main.arn
}

output "scheduler_role_name" {
  value = aws_iam_role.scheduler.name
}

output "scheduler_role_arn" {
  value = aws_iam_role.scheduler.arn
}

