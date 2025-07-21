# Imports
import os
import sys
import re
import textwrap
from typing import List, Tuple

# Function to extract vertices from polyPDF
def extractPolyPoints(polyFDF):
    # Check if polyFDF can be found
    if(os.path.isfile(polyFDF) == False):
        sys.exit("Error: your room markup FDF file cannot be found.")
    else:
        print("File found, scanning...")

    with open(polyFDF, 'r', encoding='latin-1') as file:
        content = file.read()

    pattern = re.compile(r"/Vertices\s*\[([^\]]+)\]") # Finds '/Vertices[]' and extracts all numbers inside
    matches = pattern.findall(content)

    polyPoints = []

    for match in matches:
        try:
            numbers = list(map(float, match.strip().split()))
            coords = list(zip(numbers[::2], numbers[1::2]))  # (x1, y1), (x2, y2), ...
            polyPoints.append(coords)
        except ValueError:
            print(f"⚠️ Could not parse this block: {match}")

    return polyPoints

# Function to find centre points of polygons
def extractPolyCentres(polyPointsList):
    centroids = []

    for polyPoints in polyPointsList:
        if not polyPoints:
            centroids.append(None)
            continue

        x_coords = [pt[0] for pt in polyPoints]
        y_coords = [pt[1] for pt in polyPoints]

        cx = sum(x_coords) / len(polyPoints)
        cy = sum(y_coords) / len(polyPoints)

        centroids.append((cx, cy))

    return centroids # Returns 1 set of (x, y) coordinates for each polygon, in a list [(x1, y1), (x2, y2), ...]

# Create new markup FDF


# Main function
def main():
    print("Please input room markup FDF file")
    polyFDF = input()

    polyPoints = extractPolyPoints(polyFDF)

    for i, poly in enumerate(polyPoints, 1):
        print(f"\nPolygon {i}:")
        for x, y in poly:
            print(f"({x}, {y})")

    polyCentres = extractPolyCentres(polyPoints)

    for i, (cx, cy) in enumerate(polyCentres, 1):
        print(f"Centroid of Polygon {i}: ({cx}, {cy})")
    

# Main function run
if __name__ == "__main__":
    main()