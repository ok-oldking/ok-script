# Define the paths
$buildDir = "my_build"
$sourceDir = "ok"
$rootBuildDir = "build"
$originalLocation = Get-Location

try {
    # Remove the build directory if it exists
    if (Test-Path -Path $buildDir) {
        Remove-Item -Path $buildDir -Recurse -Force
        Write-Output "Removed existing directory: $buildDir"
    }

    # Create the build directory
    New-Item -Path $buildDir -ItemType "Directory"
    Write-Output "Created new directory: $buildDir"

    # Copy the contents of the source directory to the build directory
    Copy-Item -Path "$sourceDir" -Destination $buildDir -Recurse
    Write-Output "Copied contents from $sourceDir to $buildDir"

    # Copy additional files
    Copy-Item -Path "setup.py" -Destination $buildDir -Recurse
    Copy-Item -Path "get_pypi_latest_version.py" -Destination $buildDir -Recurse
    Copy-Item -Path "MANIFEST.in" -Destination $buildDir -Recurse
    Copy-Item -Path "README.md" -Destination $buildDir -Recurse

    # Change directory to the build directory
    Set-Location $buildDir

    python setup.py sdist bdist_wheel
    if ($LASTEXITCODE -ne 0) {
        throw "python setup.py sdist bdist_wheel failed with exit code $LASTEXITCODE"
    }

    twine upload dist/*
    if ($LASTEXITCODE -ne 0) {
        throw "twine upload failed with exit code $LASTEXITCODE"
    }
}
finally {
    Set-Location $originalLocation

    foreach ($dir in @($rootBuildDir, $buildDir)) {
        $resolved = Resolve-Path -LiteralPath $dir -ErrorAction SilentlyContinue
        if ($resolved) {
            Remove-Item -LiteralPath $resolved.Path -Recurse -Force
            Write-Output "Removed directory: $dir"
        }
    }
}
