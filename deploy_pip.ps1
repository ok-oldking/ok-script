# Define the paths
$buildDir = "my_build"
$sourceDir = "ok"

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
Copy-Item -Path "MANIFEST.in" -Destination $buildDir -Recurse
Copy-Item -Path "README.md" -Destination $buildDir -Recurse

# Delete all .pyd files in the build directory
Get-ChildItem -Path $buildDir -Recurse -Filter *.pyd | Remove-Item -Force
Write-Output "Deleted all .pyd files in the build directory"

Get-ChildItem -Path $buildDir -Recurse -Filter *.cpp | Remove-Item -Force
Write-Output "Deleted all .cpp files in the build directory"

# Change directory to the build directory
cd $buildDir

python setup.py sdist bdist_wheel
twine upload dist/*

cd ..