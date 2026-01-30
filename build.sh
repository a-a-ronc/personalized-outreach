#!/bin/bash
set -e

echo "Building React frontend..."
cd dashboard
npm install
npm run build
cd ..

echo "Build complete!"
