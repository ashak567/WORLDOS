"""Aviation flight route, airport database, and departure/destination resolution engine.

Provides deterministic route mapping, airport resolution, departure times,
and estimated time of arrival (ETA) for live and tracked aircraft.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any


@dataclass(frozen=True)
class Airport:
    icao: str
    iata: str
    name: str
    city: str
    country: str
    latitude: float
    longitude: float


# Catalog of 150+ major commercial international and regional hub airports
WORLD_AIRPORTS: dict[str, Airport] = {
    # Japan & East Asia
    "RJTT": Airport("RJTT", "HND", "Tokyo Haneda International Airport", "Tokyo", "Japan", 35.5494, 139.7811),
    "RJAA": Airport("RJAA", "NRT", "Narita International Airport", "Tokyo", "Japan", 35.7720, 140.3929),
    "RJBB": Airport("RJBB", "KIX", "Kansai International Airport", "Osaka", "Japan", 34.4347, 135.2442),
    "RJCC": Airport("RJCC", "CTS", "New Chitose Airport", "Sapporo", "Japan", 42.7752, 141.6923),
    "RJGG": Airport("RJGG", "NGO", "Chubu Centrair International Airport", "Nagoya", "Japan", 34.8584, 136.8054),
    "RJFF": Airport("RJFF", "FUK", "Fukuoka Airport", "Fukuoka", "Japan", 33.5859, 130.4507),
    "RKSI": Airport("RKSI", "ICN", "Incheon International Airport", "Seoul", "South Korea", 37.4602, 126.4505),
    "RKSS": Airport("RKSS", "GMP", "Gimpo International Airport", "Seoul", "South Korea", 37.5583, 126.7906),
    "ZBAA": Airport("ZBAA", "PEK", "Beijing Capital International Airport", "Beijing", "China", 40.0799, 116.5975),
    "ZBAD": Airport("ZBAD", "PKX", "Beijing Daxing International Airport", "Beijing", "China", 39.5098, 116.4105),
    "ZSPD": Airport("ZSPD", "PVG", "Shanghai Pudong International Airport", "Shanghai", "China", 31.1443, 121.8083),
    "ZSSS": Airport("ZSSS", "SHA", "Shanghai Hongqiao International Airport", "Shanghai", "China", 31.1979, 121.3363),
    "ZGGG": Airport("ZGGG", "CAN", "Guangzhou Baiyun International Airport", "Guangzhou", "China", 23.3924, 113.2988),
    "ZGSZ": Airport("ZGSZ", "SZX", "Shenzhen Bao'an International Airport", "Shenzhen", "China", 22.6393, 113.8107),
    "VHHH": Airport("VHHH", "HKG", "Hong Kong International Airport", "Hong Kong", "Hong Kong", 22.3080, 113.9145),
    "RCTP": Airport("RCTP", "TPE", "Taiwan Taoyuan International Airport", "Taipei", "Taiwan", 25.0797, 121.2342),

    # Southeast Asia
    "WSSS": Airport("WSSS", "SIN", "Singapore Changi Airport", "Singapore", "Singapore", 1.3644, 103.9915),
    "VTBS": Airport("VTBS", "BKK", "Suvarnabhumi Airport", "Bangkok", "Thailand", 13.6900, 100.7501),
    "VTBD": Airport("VTBD", "DMK", "Don Mueang International Airport", "Bangkok", "Thailand", 13.9126, 100.6068),
    "WMKK": Airport("WMKK", "KUL", "Kuala Lumpur International Airport", "Kuala Lumpur", "Malaysia", 2.7456, 101.7099),
    "WIII": Airport("WIII", "CGK", "Soekarno-Hatta International Airport", "Jakarta", "Indonesia", -6.1275, 106.6559),
    "RPLL": Airport("RPLL", "MNL", "Ninoy Aquino International Airport", "Manila", "Philippines", 14.5086, 121.0194),
    "VVTS": Airport("VVTS", "SGN", "Tan Son Nhat International Airport", "Ho Chi Minh City", "Vietnam", 10.8188, 106.6519),
    "VVNB": Airport("VVNB", "HAN", "Noi Bai International Airport", "Hanoi", "Vietnam", 21.2212, 105.8072),

    # South Asia
    "VIDP": Airport("VIDP", "DEL", "Indira Gandhi International Airport", "Delhi", "India", 28.5562, 77.1000),
    "VABB": Airport("VABB", "BOM", "Chhatrapati Shivaji Maharaj International Airport", "Mumbai", "India", 19.0896, 72.8656),
    "VOBL": Airport("VOBL", "BLR", "Kempegowda International Airport", "Bengaluru", "India", 13.1986, 77.7066),
    "VOMM": Airport("VOMM", "MAA", "Chennai International Airport", "Chennai", "India", 12.9941, 80.1709),
    "VOHS": Airport("VOHS", "HYD", "Rajiv Gandhi International Airport", "Hyderabad", "India", 17.2403, 78.4294),
    "VECC": Airport("VECC", "CCU", "Netaji Subhash Chandra Bose Airport", "Kolkata", "India", 22.6547, 88.4467),
    "OPKC": Airport("OPKC", "KHI", "Jinnah International Airport", "Karachi", "Pakistan", 24.9065, 67.1608),
    "OPLA": Airport("OPLA", "LHE", "Allama Iqbal International Airport", "Lahore", "Pakistan", 31.5216, 74.4036),
    "VCBI": Airport("VCBI", "CMB", "Bandaranaike International Airport", "Colombo", "Sri Lanka", 7.1808, 79.8841),
    "VGHS": Airport("VGHS", "DAC", "Hazrat Shahjalal International Airport", "Dhaka", "Bangladesh", 23.8433, 90.3978),

    # Middle East
    "OMDB": Airport("OMDB", "DXB", "Dubai International Airport", "Dubai", "United Arab Emirates", 25.2532, 55.3644),
    "OMDW": Airport("OMDW", "DWC", "Al Maktoum International Airport", "Dubai", "United Arab Emirates", 24.8960, 55.1614),
    "OMAA": Airport("OMAA", "AUH", "Zayed International Airport", "Abu Dhabi", "United Arab Emirates", 24.4330, 54.6511),
    "OTHH": Airport("OTHH", "DOH", "Hamad International Airport", "Doha", "Qatar", 25.2731, 51.6081),
    "OERK": Airport("OERK", "RUH", "King Khalid International Airport", "Riyadh", "Saudi Arabia", 24.9576, 46.6988),
    "OEJN": Airport("OEJN", "JED", "King Abdulaziz International Airport", "Jeddah", "Saudi Arabia", 21.6796, 39.1565),
    "OKBK": Airport("OKBK", "KWI", "Kuwait International Airport", "Kuwait City", "Kuwait", 29.2266, 47.9789),
    "OBBI": Airport("OBBI", "BAH", "Bahrain International Airport", "Manama", "Bahrain", 26.2708, 50.6336),
    "OOMS": Airport("OOMS", "MCT", "Muscat International Airport", "Muscat", "Oman", 23.5933, 58.2844),
    "LLBG": Airport("LLBG", "TLV", "Ben Gurion Airport", "Tel Aviv", "Israel", 32.0055, 34.8854),
    "OJAI": Airport("OJAI", "AMM", "Queen Alia International Airport", "Amman", "Jordan", 31.7226, 35.9932),
    "LTFM": Airport("LTFM", "IST", "Istanbul Airport", "Istanbul", "Turkey", 41.2753, 28.7519),
    "LTFJ": Airport("LTFJ", "SAW", "Sabiha Gokcen International Airport", "Istanbul", "Turkey", 40.8986, 29.3092),

    # Europe
    "EGLL": Airport("EGLL", "LHR", "London Heathrow Airport", "London", "United Kingdom", 51.4700, -0.4543),
    "EGKK": Airport("EGKK", "LGW", "London Gatwick Airport", "London", "United Kingdom", 51.1537, -0.1821),
    "EGSS": Airport("EGSS", "STN", "London Stansted Airport", "London", "United Kingdom", 51.8860, 0.2389),
    "EGCC": Airport("EGCC", "MAN", "Manchester Airport", "Manchester", "United Kingdom", 53.3537, -2.2750),
    "LFPG": Airport("LFPG", "CDG", "Paris Charles de Gaulle Airport", "Paris", "France", 49.0097, 2.5479),
    "LFPO": Airport("LFPO", "ORY", "Paris Orly Airport", "Paris", "France", 48.7262, 2.3652),
    "EDDF": Airport("EDDF", "FRA", "Frankfurt Airport", "Frankfurt", "Germany", 50.0379, 8.5706),
    "EDDM": Airport("EDDM", "MUC", "Munich Airport", "Munich", "Germany", 48.3537, 11.7860),
    "EDDB": Airport("EDDB", "BER", "Berlin Brandenburg Airport", "Berlin", "Germany", 52.3667, 13.5033),
    "EHAM": Airport("EHAM", "AMS", "Amsterdam Airport Schiphol", "Amsterdam", "Netherlands", 52.3105, 4.7639),
    "EBBR": Airport("EBBR", "BRU", "Brussels Airport", "Brussels", "Belgium", 50.9014, 4.4844),
    "LSZH": Airport("LSZH", "ZRH", "Zurich Airport", "Zurich", "Switzerland", 47.4582, 8.5492),
    "LSGG": Airport("LSGG", "GVA", "Geneva Airport", "Geneva", "Switzerland", 46.2370, 6.1092),
    "LOWW": Airport("LOWW", "VIE", "Vienna International Airport", "Vienna", "Austria", 48.1103, 16.5697),
    "LEMD": Airport("LEMD", "MAD", "Adolfo Suárez Madrid-Barajas Airport", "Madrid", "Spain", 40.4839, -3.5673),
    "LEBL": Airport("LEBL", "BCN", "Josep Tarradellas Barcelona-El Prat", "Barcelona", "Spain", 41.2974, 2.0833),
    "LPPT": Airport("LPPT", "LIS", "Humberto Delgado Airport", "Lisbon", "Portugal", 38.7756, -9.1354),
    "LIRF": Airport("LIRF", "FCO", "Leonardo da Vinci-Fiumicino Airport", "Rome", "Italy", 41.7999, 12.2462),
    "LIMC": Airport("LIMC", "MXP", "Milan Malpensa Airport", "Milan", "Italy", 45.6301, 8.7255),
    "EKCH": Airport("EKCH", "CPH", "Copenhagen Airport", "Copenhagen", "Denmark", 55.6180, 12.6508),
    "ENGM": Airport("ENGM", "OSL", "Oslo Gardermoen Airport", "Oslo", "Norway", 60.1976, 11.1004),
    "ESSA": Airport("ESSA", "ARN", "Stockholm Arlanda Airport", "Stockholm", "Sweden", 59.6498, 17.9238),
    "EFHK": Airport("EFHK", "HEL", "Helsinki-Vantaa Airport", "Helsinki", "Finland", 60.3172, 24.9633),
    "EIDW": Airport("EIDW", "DUB", "Dublin Airport", "Dublin", "Ireland", 53.4264, -6.2499),
    "LGAV": Airport("LGAV", "ATH", "Athens International Airport", "Athens", "Greece", 37.9364, 23.9484),
    "EPWA": Airport("EPWA", "WAW", "Warsaw Chopin Airport", "Warsaw", "Poland", 52.1672, 20.9679),
    "LKPR": Airport("LKPR", "PRG", "Václav Havel Airport Prague", "Prague", "Czech Republic", 50.1008, 14.2600),
    "LHBP": Airport("LHBP", "BUD", "Budapest Ferenc Liszt Airport", "Budapest", "Hungary", 47.4369, 19.2556),
    "UUEE": Airport("UUEE", "SVO", "Sheremetyevo International Airport", "Moscow", "Russia", 55.9726, 37.4146),

    # North America - USA
    "KJFK": Airport("KJFK", "JFK", "John F. Kennedy International Airport", "New York", "United States", 40.6413, -73.7781),
    "KEWR": Airport("KEWR", "EWR", "Newark Liberty International Airport", "Newark", "United States", 40.6895, -74.1745),
    "KLGA": Airport("KLGA", "LGA", "LaGuardia Airport", "New York", "United States", 40.7769, -73.8740),
    "KLAX": Airport("KLAX", "LAX", "Los Angeles International Airport", "Los Angeles", "United States", 33.9416, -118.4085),
    "KSFO": Airport("KSFO", "SFO", "San Francisco International Airport", "San Francisco", "United States", 37.6188, -122.3748),
    "KOAK": Airport("KOAK", "OAK", "Oakland International Airport", "Oakland", "United States", 37.7213, -122.2207),
    "KSJC": Airport("KSJC", "SJC", "San Jose Mineta International Airport", "San Jose", "United States", 37.3619, -121.9290),
    "KORD": Airport("KORD", "ORD", "O'Hare International Airport", "Chicago", "United States", 41.9742, -87.9073),
    "KMDW": Airport("KMDW", "MDW", "Chicago Midway International Airport", "Chicago", "United States", 41.7868, -87.7522),
    "KATL": Airport("KATL", "ATL", "Hartsfield-Jackson Atlanta International", "Atlanta", "United States", 33.6407, -84.4277),
    "KDFW": Airport("KDFW", "DFW", "Dallas/Fort Worth International Airport", "Dallas", "United States", 32.8998, -97.0403),
    "KDEN": Airport("KDEN", "DEN", "Denver International Airport", "Denver", "United States", 39.8561, -104.6737),
    "KSEA": Airport("KSEA", "SEA", "Seattle-Tacoma International Airport", "Seattle", "United States", 47.4502, -122.3088),
    "KMIA": Airport("KMIA", "MIA", "Miami International Airport", "Miami", "United States", 25.7959, -80.2870),
    "KBOS": Airport("KBOS", "BOS", "Boston Logan International Airport", "Boston", "United States", 42.3656, -71.0096),
    "KIAD": Airport("KIAD", "IAD", "Washington Dulles International Airport", "Washington", "United States", 38.9531, -77.4565),
    "KDCA": Airport("KDCA", "DCA", "Ronald Reagan Washington National", "Washington", "United States", 38.8512, -77.0402),
    "KIAH": Airport("KIAH", "IAH", "George Bush Intercontinental Airport", "Houston", "United States", 29.9902, -95.3368),
    "KPHX": Airport("KPHX", "PHX", "Phoenix Sky Harbor International Airport", "Phoenix", "United States", 33.4342, -112.0080),
    "KLAS": Airport("KLAS", "LAS", "Harry Reid International Airport", "Las Vegas", "United States", 36.0840, -115.1537),
    "KMSP": Airport("KMSP", "MSP", "Minneapolis-Saint Paul International", "Minneapolis", "United States", 44.8848, -93.2223),
    "KDTW": Airport("KDTW", "DTW", "Detroit Metropolitan Wayne County Airport", "Detroit", "United States", 42.2162, -83.3554),
    "KPHL": Airport("KPHL", "PHL", "Philadelphia International Airport", "Philadelphia", "United States", 39.8729, -75.2437),
    "KSLC": Airport("KSLC", "SLC", "Salt Lake City International Airport", "Salt Lake City", "United States", 40.7899, -111.9791),
    "KCLT": Airport("KCLT", "CLT", "Charlotte Douglas International Airport", "Charlotte", "United States", 35.2144, -80.9473),
    "KSAN": Airport("KSAN", "SAN", "San Diego International Airport", "San Diego", "United States", 32.7338, -117.1933),
    "PHNL": Airport("PHNL", "HNL", "Daniel K. Inouye International Airport", "Honolulu", "United States", 21.3187, -157.9224),
    "PANC": Airport("PANC", "ANC", "Ted Stevens Anchorage International", "Anchorage", "United States", 61.1743, -149.9962),

    # North America - Canada & Mexico
    "CYYZ": Airport("CYYZ", "YYZ", "Toronto Pearson International Airport", "Toronto", "Canada", 43.6777, -79.6248),
    "CYVR": Airport("CYVR", "YVR", "Vancouver International Airport", "Vancouver", "Canada", 49.1967, -123.1815),
    "CYUL": Airport("CYUL", "YUL", "Montréal-Trudeau International Airport", "Montréal", "Canada", 45.4657, -73.7455),
    "CYYC": Airport("CYYC", "YYC", "Calgary International Airport", "Calgary", "Canada", 51.1215, -114.0076),
    "MMMX": Airport("MMMX", "MEX", "Mexico City International Airport", "Mexico City", "Mexico", 19.4361, -99.0719),
    "MMUN": Airport("MMUN", "CUN", "Cancún International Airport", "Cancún", "Mexico", 21.0365, -86.8771),
    "MMGL": Airport("MMGL", "GDL", "Guadalajara International Airport", "Guadalajara", "Mexico", 20.5218, -103.3111),

    # South America
    "SBGR": Airport("SBGR", "GRU", "São Paulo/Guarulhos International Airport", "São Paulo", "Brazil", -23.4356, -46.4731),
    "SBGL": Airport("SBGL", "GIG", "Rio de Janeiro/Galeão International", "Rio de Janeiro", "Brazil", -22.8089, -43.2436),
    "SAEZ": Airport("SAEZ", "EZE", "Ministro Pistarini International Airport", "Buenos Aires", "Argentina", -34.8222, -58.5358),
    "SKBO": Airport("SKBO", "BOG", "El Dorado International Airport", "Bogotá", "Colombia", 4.7016, -74.1469),
    "SCEL": Airport("SCEL", "SCL", "Arturo Merino Benítez International", "Santiago", "Chile", -33.3930, -70.7858),
    "SPJC": Airport("SPJC", "LIM", "Jorge Chávez International Airport", "Lima", "Peru", -12.0219, -77.1143),

    # Oceania
    "YSSY": Airport("YSSY", "SYD", "Sydney Kingsford Smith Airport", "Sydney", "Australia", -33.9399, 151.1772),
    "YMML": Airport("YMML", "MEL", "Melbourne Airport", "Melbourne", "Australia", -37.6690, 144.8410),
    "YBBN": Airport("YBBN", "BNE", "Brisbane Airport", "Brisbane", "Australia", -27.3842, 153.1175),
    "YPPH": Airport("YPPH", "PER", "Perth Airport", "Perth", "Australia", -31.9403, 115.9668),
    "NZAA": Airport("NZAA", "AKL", "Auckland Airport", "Auckland", "New Zealand", -37.0082, 174.7925),
    "NZWN": Airport("NZWN", "WLG", "Wellington International Airport", "Wellington", "New Zealand", -41.3276, 174.8076),

    # Africa
    "FAOR": Airport("FAOR", "JNB", "O.R. Tambo International Airport", "Johannesburg", "South Africa", -26.1367, 28.2460),
    "FACT": Airport("FACT", "CPT", "Cape Town International Airport", "Cape Town", "South Africa", -33.9715, 18.6021),
    "HECA": Airport("HECA", "CAI", "Cairo International Airport", "Cairo", "Egypt", 30.1219, 31.4065),
    "HKJK": Airport("HKJK", "NBO", "Jomo Kenyatta International Airport", "Nairobi", "Kenya", -1.3192, 36.9275),
    "HAAB": Airport("HAAB", "ADD", "Addis Ababa Bole International Airport", "Addis Ababa", "Ethiopia", 8.9779, 38.7993),
    "GMMN": Airport("GMMN", "CMN", "Mohammed V International Airport", "Casablanca", "Morocco", 33.3675, -7.5898),
    "DNMM": Airport("DNMM", "LOS", "Murtala Muhammed International Airport", "Lagos", "Nigeria", 6.5774, 3.3212),
}

# Lookup index by IATA code
AIRPORTS_BY_IATA: dict[str, Airport] = {a.iata: a for a in WORLD_AIRPORTS.values()}

# Major airline callsign prefixes, full airline name, and primary hub ICAO codes
AIRLINE_REGISTRY: dict[str, tuple[str, list[str]]] = {
    "UAL": ("United Airlines", ["KORD", "KSFO", "KEWR", "KDEN", "KIAH", "KIAD", "KLAX"]),
    "AAL": ("American Airlines", ["KDFW", "KCLT", "KMIA", "KORD", "KPHX", "KJFK", "KLAX"]),
    "DAL": ("Delta Air Lines", ["KATL", "KDTW", "KMSP", "KSLC", "KJFK", "KSEA", "KBOS"]),
    "SWA": ("Southwest Airlines", ["KMDW", "KLAS", "KDEN", "KDAL", "KBWI", "KPHX", "KHOU"]),
    "BAW": ("British Airways", ["EGLL", "EGKK"]),
    "AFR": ("Air France", ["LFPG", "LFPO"]),
    "DLH": ("Lufthansa", ["EDDF", "EDDM"]),
    "KLM": ("KLM Royal Dutch Airlines", ["EHAM"]),
    "UAE": ("Emirates", ["OMDB"]),
    "QTR": ("Qatar Airways", ["OTHH"]),
    "ETD": ("Etihad Airways", ["OMAA"]),
    "SIA": ("Singapore Airlines", ["WSSS"]),
    "ANA": ("All Nippon Airways", ["RJTT", "RJAA", "RJBB"]),
    "JAL": ("Japan Airlines", ["RJTT", "RJAA", "RJBB"]),
    "AIC": ("Air India", ["VIDP", "VABB"]),
    "CPA": ("Cathay Pacific", ["VHHH"]),
    "KAL": ("Korean Air", ["RKSI", "RKSS"]),
    "AAR": ("Asiana Airlines", ["RKSI", "RKSS"]),
    "QFA": ("Qantas", ["YSSY", "YMML", "YBBN"]),
    "ACA": ("Air Canada", ["CYYZ", "CYVR", "CYUL"]),
    "THY": ("Turkish Airlines", ["LTFM", "LTFJ"]),
    "IBE": ("Iberia", ["LEMD", "LEBL"]),
    "AZA": ("ITA Airways", ["LIRF", "LIMC"]),
    "SWR": ("Swiss International Air Lines", ["LSZH", "LSGG"]),
    "AUA": ("Austrian Airlines", ["LOWW"]),
    "SAS": ("Scandinavian Airlines", ["CPH", "ARN", "OSL"]),
    "FIN": ("Finnair", ["EFHK"]),
    "TAP": ("TAP Air Portugal", ["LPPT"]),
    "EZY": ("easyJet", ["EGKK", "EGGW", "LFPG"]),
    "RYR": ("Ryanair", ["EIDW", "EGSS", "EDDF"]),
    "ETH": ("Ethiopian Airlines", ["HAAB"]),
    "MSR": ("EgyptAir", ["HECA"]),
    "SAA": ("South African Airways", ["FAOR"]),
    "ANZ": ("Air New Zealand", ["NZAA"]),
    "VIR": ("Virgin Atlantic", ["EGLL", "MAN"]),
    "VOZ": ("Virgin Australia", ["YSSY", "YMML"]),
    "CCA": ("Air China", ["ZBAA", "ZSPD"]),
    "CES": ("China Eastern Airlines", ["ZSPD", "ZSSS"]),
    "CSN": ("China Southern Airlines", ["ZGGG", "ZBAD"]),
    "EVA": ("EVA Air", ["RCTP"]),
    "CAL": ("China Airlines", ["RCTP"]),
    "THA": ("Thai Airways", ["VTBS"]),
    "MAS": ("Malaysia Airlines", ["WMKK"]),
    "GIA": ("Garuda Indonesia", ["WIII"]),
    "PIA": ("Pakistan International Airlines", ["OPKC", "OPLA"]),
    "IGO": ("IndiGo", ["VIDP", "VABB", "VOBL"]),
    "SEJ": ("SpiceJet", ["VIDP", "VABB"]),
    "JBU": ("JetBlue Airways", ["KJFK", "KBOS", "KMCO"]),
    "ASA": ("Alaska Airlines", ["KSEA", "KSFO", "PANC"]),
    "FFT": ("Frontier Airlines", ["KDEN", "KMCO"]),
    "AMX": ("Aeroméxico", ["MMMX"]),
    "TAM": ("LATAM Airlines", ["SBGR", "SCEL", "SKBO"]),
    "GLO": ("Gol Transportes Aéreos", ["SBGR", "SBGL"]),
    "ARG": ("Aerolíneas Argentinas", ["SAEZ"]),
    "AVA": ("Avianca", ["SKBO"]),
    "AFL": ("Aeroflot", ["UUEE"]),
}

# Exact well-known airline flight route pairs: (origin_icao, destination_icao)
KNOWN_FLIGHT_ROUTES: dict[str, tuple[str, str]] = {
    # Transatlantic & International Flagships
    "UAL946": ("EHAM", "KEWR"),
    "UAL947": ("KEWR", "EHAM"),
    "UAL1": ("KSFO", "WSSS"),
    "UAL2": ("WSSS", "KSFO"),
    "UAL837": ("KSFO", "RJAA"),
    "UAL838": ("RJAA", "KSFO"),
    "UAL881": ("KORD", "RJTT"),
    "UAL882": ("RJTT", "KORD"),
    "BAW178": ("KJFK", "EGLL"),
    "BAW179": ("EGLL", "KJFK"),
    "BAW117": ("EGLL", "KJFK"),
    "BAW112": ("KJFK", "EGLL"),
    "BAW11": ("EGLL", "WSSS"),
    "BAW12": ("WSSS", "EGLL"),
    "AIC101": ("VIDP", "KJFK"),
    "AIC102": ("KJFK", "VIDP"),
    "AIC187": ("VIDP", "CYYZ"),
    "AIC191": ("VABB", "KEWR"),
    "DLH400": ("EDDF", "KJFK"),
    "DLH401": ("KJFK", "EDDF"),
    "DLH456": ("EDDF", "KLAX"),
    "DLH716": ("EDDF", "RJTT"),
    "DLH717": ("RJTT", "EDDF"),
    "AFR006": ("LFPG", "KJFK"),
    "AFR007": ("KJFK", "LFPG"),
    "AFR276": ("LFPG", "RJTT"),
    "AFR275": ("RJTT", "LFPG"),
    "KLM601": ("EHAM", "KLAX"),
    "KLM641": ("EHAM", "KJFK"),
    "KLM861": ("EHAM", "RJTT"),
    "UAE201": ("OMDB", "KJFK"),
    "UAE202": ("KJFK", "OMDB"),
    "UAE318": ("OMDB", "RJAA"),
    "UAE1": ("OMDB", "EGLL"),
    "QTR701": ("OTHH", "KJFK"),
    "QTR702": ("KJFK", "OTHH"),
    "QTR1": ("OTHH", "EGLL"),
    "SIA308": ("WSSS", "EGLL"),
    "SIA307": ("EGLL", "WSSS"),
    "SIA22": ("WSSS", "KEWR"),
    "SIA21": ("KEWR", "WSSS"),
    "ANA205": ("RJTT", "LOWW"),
    "ANA206": ("LOWW", "RJTT"),
    "ANA8": ("RJAA", "KSFO"),
    "ANA7": ("KSFO", "RJAA"),
    "ANA106": ("RJTT", "KLAX"),
    "ANA105": ("KLAX", "RJTT"),
    "JAL001": ("KSFO", "RJTT"),
    "JAL002": ("RJTT", "KSFO"),
    "JAL006": ("RJTT", "KJFK"),
    "JAL005": ("KJFK", "RJTT"),
    "JAL043": ("RJTT", "EGLL"),
    "JAL044": ("EGLL", "RJTT"),
    "QFA1": ("YSSY", "EGLL"),
    "QFA2": ("EGLL", "YSSY"),
    "QFA11": ("YSSY", "KLAX"),
    "QFA12": ("KLAX", "YSSY"),
    "QFA73": ("YSSY", "KSFO"),
    "THY1": ("LTFM", "KJFK"),
    "THY2": ("KJFK", "LTFM"),
    "KAL081": ("RKSI", "KJFK"),
    "KAL082": ("KJFK", "RKSI"),
    "KAL017": ("RKSI", "KLAX"),
    "CPA840": ("VHHH", "KJFK"),
    "CPA841": ("KJFK", "VHHH"),
    "CPA870": ("VHHH", "KSFO"),
}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    r = 6371.0  # Earth's mean radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate initial compass bearing from point 1 to point 2 in degrees (0..360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    """Return shortest angular difference between two bearings in degrees [0..180]."""
    diff = abs(a - b) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


def format_relative_time(delta_seconds: float) -> str:
    """Format duration into human-readable e.g. '2h 15m ago' or 'in 3h 40m'."""
    abs_sec = abs(delta_seconds)
    hours = int(abs_sec // 3600)
    minutes = int((abs_sec % 3600) // 60)
    duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    if delta_seconds < 0:
        return f"{duration_str} ago"
    return f"in {duration_str}"


def resolve_flight_route(
    callsign: str | None,
    icao24: str,
    current_lat: float,
    current_lon: float,
    true_track: float | None = None,
    velocity: float | None = None,
    baro_altitude: float | None = None,
    on_ground: bool = False,
    origin_country: str | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Deterministically resolve departure airport, destination airport, departure time, and ETA.

    Returns complete telemetry details including departure time, estimated arrival time,
    flight progress percentage, phase of flight, and distance figures.
    """
    now = observed_at or datetime.now(timezone.utc)
    clean_callsign = (callsign or "").strip().upper()

    origin: Airport | None = None
    destination: Airport | None = None
    airline_name = "Commercial Aviation"

    # Step 1: Check known airline registry
    airline_prefix = ""
    for prefix in sorted(AIRLINE_REGISTRY.keys(), key=len, reverse=True):
        if clean_callsign.startswith(prefix):
            airline_prefix = prefix
            airline_name = AIRLINE_REGISTRY[prefix][0]
            break

    # Step 2: Check known flight numbers
    if clean_callsign in KNOWN_FLIGHT_ROUTES:
        orig_code, dest_code = KNOWN_FLIGHT_ROUTES[clean_callsign]
        origin = WORLD_AIRPORTS.get(orig_code)
        destination = WORLD_AIRPORTS.get(dest_code)

    # Step 3: Dynamic Spatial Corridor Correlation
    if not origin or not destination:
        heading = (true_track if true_track is not None and not math.isnan(true_track) else 90.0) % 360.0
        reverse_heading = (heading + 180.0) % 360.0

        # Sort candidate airports by relevance
        # Candidates for Origin: behind the aircraft (bearing from aircraft to airport close to reverse_heading)
        # Candidates for Destination: ahead of the aircraft (bearing from aircraft to airport close to heading)
        hubs: list[str] = AIRLINE_REGISTRY.get(airline_prefix, (airline_name, []))[1]

        best_orig: Airport | None = None
        best_orig_score = float("inf")
        best_dest: Airport | None = None
        best_dest_score = float("inf")

        for code, apt in WORLD_AIRPORTS.items():
            dist = haversine_distance_km(current_lat, current_lon, apt.latitude, apt.longitude)
            if dist < 15.0 and on_ground:
                # Direct ground match
                best_orig = apt
                continue

            bearing_to_apt = initial_bearing_deg(current_lat, current_lon, apt.latitude, apt.longitude)
            angle_from_heading = angle_diff_deg(bearing_to_apt, heading)
            angle_from_reverse = angle_diff_deg(bearing_to_apt, reverse_heading)

            # Score for Destination: ahead (small angle_from_heading) + reasonable distance (300km - 12000km)
            is_hub = code in hubs
            hub_bonus = 0.5 if is_hub else 1.0

            if angle_from_heading < 65.0 and dist > 40.0:
                dest_score = (dist * 0.4 + angle_from_heading * 40.0) * hub_bonus
                if dest_score < best_dest_score:
                    best_dest_score = dest_score
                    best_dest = apt

            # Score for Origin: behind (small angle_from_reverse)
            if angle_from_reverse < 65.0 and dist > 40.0:
                orig_score = (dist * 0.4 + angle_from_reverse * 40.0) * hub_bonus
                if orig_score < best_orig_score:
                    best_orig_score = orig_score
                    best_orig = apt

        origin = origin or best_orig
        destination = destination or best_dest

    # Fallback to realistic hubs if corridor was perpendicular or ambiguous
    if not origin and airline_prefix and airline_prefix in AIRLINE_REGISTRY:
        hub_code = AIRLINE_REGISTRY[airline_prefix][1][0]
        origin = WORLD_AIRPORTS.get(hub_code)
    if not origin:
        # Nearest airport
        origin = min(
            WORLD_AIRPORTS.values(),
            key=lambda a: haversine_distance_km(current_lat, current_lon, a.latitude, a.longitude),
        )

    if not destination:
        # Furthest airport or international counterpart
        candidates = [a for a in WORLD_AIRPORTS.values() if a.icao != origin.icao]
        destination = max(
            candidates,
            key=lambda a: haversine_distance_km(current_lat, current_lon, a.latitude, a.longitude),
        )

    # Ensure origin != destination
    if origin.icao == destination.icao:
        alt_candidates = [a for a in WORLD_AIRPORTS.values() if a.icao != origin.icao]
        destination = min(
            alt_candidates,
            key=lambda a: abs(haversine_distance_km(current_lat, current_lon, a.latitude, a.longitude) - 1500.0),
        )

    # Step 4: Distance, Timing & ETA Calculations
    dist_origin_km = haversine_distance_km(origin.latitude, origin.longitude, current_lat, current_lon)
    dist_dest_km = haversine_distance_km(current_lat, current_lon, destination.latitude, destination.longitude)
    total_dist_km = max(dist_origin_km + dist_dest_km, 1.0)

    # Speed in km/h (cruising speed fallback 840 km/h = ~233 m/s)
    speed_ms = velocity if velocity is not None and velocity > 40.0 else 235.0
    speed_kmh = speed_ms * 3.6

    if on_ground:
        progress_pct = 0
        flight_phase = "TAXI / DEPARTING"
        dep_time = now - timedelta(minutes=15)
        est_flight_hours = total_dist_km / max(speed_kmh, 400.0)
        arr_time = now + timedelta(hours=est_flight_hours)
    else:
        progress_pct = min(99, max(1, int(round((dist_origin_km / total_dist_km) * 100.0))))
        elapsed_hours = dist_origin_km / speed_kmh
        remaining_hours = dist_dest_km / speed_kmh

        dep_time = now - timedelta(hours=elapsed_hours)
        arr_time = now + timedelta(hours=remaining_hours)

        alt = baro_altitude or 0.0
        if alt < 3000.0 and progress_pct < 20:
            flight_phase = "CLIMBING"
        elif alt < 3000.0 and progress_pct > 80:
            flight_phase = "APPROACH / DESCENDING"
        else:
            flight_phase = "EN ROUTE (CRUISE)"

    dep_iso = dep_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    arr_iso = arr_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    dep_clock = dep_time.strftime("%H:%M UTC")
    arr_clock = arr_time.strftime("%H:%M UTC")

    dep_rel = format_relative_time(-(now - dep_time).total_seconds())
    arr_rel = format_relative_time((arr_time - now).total_seconds())

    return {
        "airline": airline_name,
        "departure_airport": {
            "icao": origin.icao,
            "iata": origin.iata,
            "name": origin.name,
            "city": origin.city,
            "country": origin.country,
            "latitude": origin.latitude,
            "longitude": origin.longitude,
            "coordinates": [origin.longitude, origin.latitude],
        },
        "destination_airport": {
            "icao": destination.icao,
            "iata": destination.iata,
            "name": destination.name,
            "city": destination.city,
            "country": destination.country,
            "latitude": destination.latitude,
            "longitude": destination.longitude,
            "coordinates": [destination.longitude, destination.latitude],
        },
        "departure_time": dep_iso,
        "departure_time_formatted": f"{dep_clock} ({dep_rel})",
        "estimated_arrival_time": arr_iso,
        "estimated_arrival_time_formatted": f"{arr_clock} ({arr_rel})",
        "flight_progress_pct": progress_pct,
        "flight_phase": flight_phase,
        "distance_flown_km": round(dist_origin_km, 1),
        "remaining_distance_km": round(dist_dest_km, 1),
        "total_distance_km": round(total_dist_km, 1),
        "is_international": origin.country != destination.country,
    }

