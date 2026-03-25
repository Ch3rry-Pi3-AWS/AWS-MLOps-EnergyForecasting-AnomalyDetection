# Expose the catalogue object names so later Glue jobs and Athena work can
# reference them without re-deriving naming conventions.
output "glue_database_name" {
  value = aws_glue_catalog_database.bronze.name
}

output "energy_table_name" {
  value = aws_glue_catalog_table.energy.name
}

output "weather_table_name" {
  value = aws_glue_catalog_table.weather.name
}

output "manifest_table_name" {
  value = aws_glue_catalog_table.manifest.name
}
