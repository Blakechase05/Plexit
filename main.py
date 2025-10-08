from Plexit.plot import *
from Plexit.algorithm import *

def main():
    # Define some random polygon points for now
    points = [(0.0, 0.0), (12.0, 0.0), (12.0, 5.0), (8.0, 5.0),
          (8.0, 6.0), (10.0, 6.0), (10.0, 10.0), (3.0, 10.0),
          (3.0, 7.0), (1.0, 7.0), (1.0, 4.0), (-2.0, 4.0),
          (-2.0, 1.0), (0.0, 1.0)]
    
    # Set up required polygon elements (polygon, path, edges)
    polygon = createPolygon(points, edgecolor='r', fill=None)
    polyPath = Path(points, closed=True)
    polySides = cutPolyPath(points)

    # for i, side in enumerate(polySides):
    #     print(f"Side {i}: {side}")
    
    dir =  removeMimics(polySides, (8.0, 5.0))
    
    removeOutsides(polyPath, (8.0, 5.0), dir)

    # print(f"Final directions: {dir}") # Debugging line

    # Plot the polygon with respect to it's boundaries
    xLim, yLim = getBounds(points)
    plotPolygon(polygon, xLim, yLim, title="Rectilinear Polygon")

if __name__ == "__main__":
    main()