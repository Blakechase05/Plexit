# Imports
import os
import sys

# Main function

def main():
    print("Please input room markup FDF file")
    polyFDF = input()

    if(os.path.isfile(polyFDF) == False):
        sys.exit("Error: your room markup FDF file cannot be found.")

    print("hello world")

# Main function run
if __name__ == "__main__":
    main()