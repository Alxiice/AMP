#!/bin/bash

# Quick script to build and run the AMP application

echo "=========================================="
echo "AMP - Another Music Player"
echo "=========================================="
echo ""

# Check if we should build the frontend
if [ "$1" = "full" ] || [ "$1" = "--full" ]; then
    echo "Building frontend..."
    cd app
    npm run build
    cd ..
    echo "Frontend built!"
    echo ""
fi

echo "Starting backend server..."
echo "Backend will be available at: http://localhost:8000"
echo ""

# Start backend in background
python amp/backend/main.py &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 3

if [ "$1" = "full" ] || [ "$1" = "--full" ]; then
    echo "Starting frontend dev server..."
    echo "Frontend will be available at: http://localhost:3000"
    echo ""
    cd app
    npm run serve
    cd ..
    # Kill backend when frontend exits
    kill $BACKEND_PID
else
    echo "Backend is running!"
    echo ""
    echo "To test authentication:"
    echo "  1. Open another terminal"
    echo "  2. Run: curl -X POST http://localhost:8000/api/auth/cookie-auth"
    echo "  3. Or use the frontend: cd app && npm run dev"
    echo ""
    echo "Press Ctrl+C to stop the backend..."
    wait $BACKEND_PID
fi
