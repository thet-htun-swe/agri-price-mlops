-- Loads S3 partition folders (year, month) into Athena metadata so Athena can see all data partitions.

MSCK REPAIR TABLE agri_mlops.agri_features_actual;
