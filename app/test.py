from app.agents.tools import search_buses,search_flights,search_train,train_get_live_status
from app.agents.tools import to_iata, to_station

# print("hello world")

# print(search_train.invoke({"source": to_station("Pune"), "destination":to_station("Mumbai") }))



# print(search_buses("pune","mumbai"))


# print(search_buses.invoke({"source": "pune", "destination": "mumbai"}))


print(train_get_live_status.invoke({"train_number": "12129 "}))
