# Static Website (S3 Hosting)

Files:
- `index.html`
- `styles.css`
- `app.js`

## 1) Update JSON URL (if needed)
Edit `app.js`:
- `DATA_URL = "https://<your-bucket>.s3.<region>.amazonaws.com/predictions/curated/latest/predictions.json"`

## 2) Upload to S3
Create (or reuse) a website bucket, then upload all files in this folder to bucket root.

## 3) Enable Static Website Hosting
S3 bucket -> `Properties` -> `Static website hosting`:
- Enable
- Index document: `index.html`

## 4) Allow public read for website files
Add bucket policy for site objects (or entire bucket in demo).  
Also ensure public access settings allow this policy.

Example policy for full bucket read:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadSite",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR_WEBSITE_BUCKET/*"
    }
  ]
}
```

## 5) Open website endpoint
Use the S3 website endpoint shown in bucket properties.
