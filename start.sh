#!/bin/bash

echo "🚀 Starting Personalized Outreach Platform..."

# Run database migration
echo "📊 Running database migration..."
python migrate_db.py

# Start backend server
echo "🔧 Starting backend server on port 7000..."
python backend/app.py &

# Wait for backend to be ready
sleep 3

echo "✅ Platform is ready!"
echo "📱 Backend API: http://localhost:7000"
echo "🎨 Dashboard: Open dashboard/index.html in browser"
echo ""
echo "To test all endpoints, run: python test_backend.py"
echo ""

# Keep script running
wait
