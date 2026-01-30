# Railway Deployment Guide

This guide will help you deploy your personalized-outreach platform to Railway.

## Prerequisites

1. A Railway account (sign up at https://railway.app)
2. Your repository on GitHub (or GitLab/Bitbucket)
3. All required API keys ready

## Step 1: Push Your Code to GitHub

If you haven't already, push your code to a GitHub repository:

```bash
git init
git add .
git commit -m "Prepare for Railway deployment"
git remote add origin YOUR_GITHUB_REPO_URL
git push -u origin master
```

## Step 2: Create a New Project on Railway

1. Go to https://railway.app
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your `personalized-outreach` repository
5. Railway will automatically detect it's a Python app

## Step 3: Configure Environment Variables

In your Railway project, go to the **Variables** tab and add these environment variables:

### REQUIRED Variables

```
OPENAI_API_KEY=your-openai-api-key-here
SENDGRID_API_KEY=your-sendgrid-api-key-here
BASE_URL=https://your-railway-app.railway.app
```

⚠️ **Important**: After deployment, Railway will give you a public URL. Come back and update `BASE_URL` with that URL.

### OPTIONAL Variables (for full functionality)

```
APOLLO_API_KEY=your-apollo-api-key-here
MAXMIND_LICENSE_KEY=your-maxmind-license-key-here
LEADFEEDER_EMAIL=your-leadfeeder-email@example.com
LEADFEEDER_PASSWORD=your-leadfeeder-password
BLAND_API_KEY=your-bland-api-key-here
LINKEDIN_EMAIL=your-linkedin-email@example.com
LINKEDIN_PASSWORD=your-linkedin-password
SCHEDULER_ENABLED=true
```

## Step 4: Deploy

1. Railway will automatically build and deploy your app
2. Wait for the deployment to complete (usually 2-5 minutes)
3. Once deployed, you'll see a public URL like `https://personalized-outreach-production-xxxx.railway.app`

## Step 5: Update BASE_URL

1. Copy your Railway app URL
2. Go back to Variables tab
3. Update `BASE_URL` to your Railway URL (e.g., `https://personalized-outreach-production-xxxx.railway.app`)
4. Railway will automatically redeploy

## Step 6: Add Custom Domain (Optional)

If you want a custom domain like `outreach.intralog.io`:

1. In Railway project, go to **Settings** → **Domains**
2. Click "Add Custom Domain"
3. Enter your domain (e.g., `outreach.intralog.io`)
4. Railway will show you DNS records to add
5. Go to GoDaddy DNS settings and add the CNAME record:
   - Type: `CNAME`
   - Name: `outreach` (or whatever subdomain you want)
   - Value: Your Railway domain
6. Wait for DNS propagation (5-30 minutes)
7. Update `BASE_URL` environment variable to your custom domain

## Step 7: Verify Deployment

Test these endpoints to confirm everything works:

1. **Health Check**: `https://your-railway-url.railway.app/api/health`
2. **Tracking Script**: `https://your-railway-url.railway.app/api/track/script.js`
3. **Visitor Analytics**: `https://your-railway-url.railway.app/api/visitors/analytics`

## Step 8: Set Up WordPress Tracking

Now that your backend is deployed, add this to your WordPress site:

```html
<script src="https://your-railway-url.railway.app/api/track/script.js" async></script>
```

Replace `your-railway-url.railway.app` with your actual Railway URL or custom domain.

## Database Persistence

Railway automatically provides persistent storage for your SQLite database. Your `leads.db` file will be preserved across deployments.

## Monitoring & Logs

- **View Logs**: In Railway project, go to the **Deployments** tab and click on your deployment
- **Monitor Usage**: Railway dashboard shows CPU, memory, and bandwidth usage
- **Set Up Alerts**: Go to **Settings** → **Notifications** to get notified of issues

## Troubleshooting

### Deployment Failed
- Check the build logs in Railway dashboard
- Ensure all required environment variables are set
- Verify your `requirements.txt` has all dependencies

### App Crashes on Start
- Check the deployment logs for error messages
- Ensure `BASE_URL` is set correctly
- Verify API keys are valid

### Visitor Tracking Not Working
- Verify `BASE_URL` is set to your Railway URL
- Check CORS is enabled (already configured in the code)
- Test the tracking script URL in your browser
- Check browser console for JavaScript errors

## Cost Estimation

Railway pricing:
- **Free tier**: $5 credit/month (usually sufficient for small projects)
- **Pro plan**: $20/month with $5 included usage
- Your app will likely use ~$5-10/month depending on traffic

## Need Help?

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Check deployment logs in Railway dashboard
