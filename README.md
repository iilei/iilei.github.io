# iilei.github.io

A simple one-pager built with [Hugo](https://gohugo.io/) and automatically deployed to GitHub Pages.

## 🚀 Setup

This repository is configured to automatically build and deploy to https://iilei.github.io/ using GitHub Actions.

### Enable GitHub Pages

To enable the deployment, you need to configure GitHub Pages:

1. Go to your repository on GitHub
2. Click on **Settings** → **Pages**
3. Under **Source**, select **GitHub Actions** (not "Deploy from a branch")
4. Save the changes

Once enabled, the site will automatically deploy on every push to the `master` or `main` branch.

**Important:** Make sure "GitHub Actions" is selected as the source, not "Deploy from a branch". If you see your README displayed instead of the site, it means GitHub Pages is still configured to deploy from a branch.

## 🛠️ Local Development

To run the site locally:

1. Install Hugo (https://gohugo.io/installation/)
2. Clone this repository
3. Run `hugo server` in the repository root
4. Open http://localhost:1313 in your browser

## 📝 Customization

- **Content**: Edit `layouts/index.html` to change the page content and styling
- **Configuration**: Edit `hugo.toml` to change site settings
- **Add pages**: Create new files in the `content/` directory

## 📦 Build

To build the site manually:

```bash
hugo --minify
```

The generated site will be in the `public/` directory.

## 🔄 Deployment

The site is automatically deployed via GitHub Actions when you push to the `master` or `main` branch. The workflow is defined in `.github/workflows/hugo.yml`.

**Note:** Ensure GitHub Pages is configured to use "GitHub Actions" as the deployment source in your repository settings (Settings → Pages → Source → GitHub Actions).
