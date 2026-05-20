$ErrorActionPreference = "Stop"

Write-Host "Running backend lint (Ruff)..."
Push-Location backend
try {
    ../.venv/Scripts/python -m ruff check app test_exif_gps.py
    if ($LASTEXITCODE -ne 0) {
        throw "Backend lint failed with exit code $LASTEXITCODE"
    }

    Write-Host "Running backend advisory guardrails (Pylint size/length/complexity)..."
    ../.venv/Scripts/python -m pylint --rcfile=.pylintrc --exit-zero app
}
finally {
    Pop-Location
}

Write-Host "Running frontend lint (Next.js ESLint)..."
Push-Location frontend
try {
    npm run lint
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend lint failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "All lint checks passed."
