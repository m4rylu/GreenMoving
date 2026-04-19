import os
from bike_class import Bike

model_name = os.getenv('BIKE_ID', 'Not Exist')

if __name__ == "__main__":
    my_bike = Bike(model_name)
    my_bike.simulation()
    print(f"I'm a bike container with ID: {model_name}")
