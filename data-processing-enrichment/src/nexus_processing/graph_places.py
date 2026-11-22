# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Places for text entity typing (data only, casefolded, packed; ``_`` stands for a space).

Countries and common short forms, continents and business regions, first-level divisions
(US states, Canadian provinces, Indian, Australian, Chinese, German, Brazilian, Mexican and
other states and regions) and several thousand cities and towns. ``graph_lexicon.places()``
builds the set on first use. ``AMBIGUOUS`` lists places that are also ordinary words, given
names or product names: they are typed ``place`` only with a place cue ("in Reading",
"the Phoenix office"), never on their own.
"""

from __future__ import annotations

PACKED = """
afghanistan albania algeria andorra angola antigua argentina armenia australia austria
azerbaijan bahamas bahrain bangladesh barbados belarus belgium belize benin bhutan bolivia
bosnia bosnia_and_herzegovina botswana brazil brunei bulgaria burkina_faso burundi cambodia
cameroon canada cape_verde central_african_republic chad chile china colombia comoros congo
costa_rica croatia cuba cyprus czechia czech_republic denmark djibouti dominica
dominican_republic east_timor ecuador egypt el_salvador equatorial_guinea eritrea estonia
eswatini ethiopia fiji finland france gabon gambia georgia germany ghana greece grenada
guatemala guinea guinea-bissau guyana haiti honduras hong_kong hungary iceland india indonesia
iran iraq ireland israel italy ivory_coast jamaica japan jordan kazakhstan kenya kiribati kosovo
kuwait kyrgyzstan laos latvia lebanon lesotho liberia libya liechtenstein lithuania luxembourg
macau madagascar malawi malaysia maldives mali malta marshall_islands mauritania mauritius
mexico micronesia moldova monaco mongolia montenegro morocco mozambique myanmar burma namibia
nauru nepal netherlands holland new_zealand nicaragua niger nigeria north_korea north_macedonia
macedonia norway oman pakistan palau palestine panama papua_new_guinea paraguay peru philippines
poland portugal puerto_rico qatar romania russia rwanda samoa san_marino saudi_arabia scotland
senegal serbia seychelles sierra_leone singapore slovakia slovenia solomon_islands somalia
south_africa south_korea korea south_sudan spain sri_lanka sudan suriname sweden switzerland
syria taiwan tajikistan tanzania thailand togo tonga trinidad trinidad_and_tobago tunisia turkey
turkiye turkmenistan tuvalu uganda ukraine united_arab_emirates uae united_kingdom britain
great_britain england wales northern_ireland united_states united_states_of_america america usa
uruguay uzbekistan vanuatu vatican venezuela vietnam viet_nam yemen zambia zimbabwe greenland
faroe_islands bermuda cayman_islands guam gibraltar curacao aruba martinique guadeloupe reunion
new_caledonia tahiti africa asia europe antarctica oceania north_america south_america
latin_america central_america middle_east near_east far_east east_asia south_asia southeast_asia
south-east_asia central_asia western_europe eastern_europe northern_europe southern_europe
central_europe scandinavia nordics benelux balkans baltics caribbean gulf persian_gulf
sub-saharan_africa west_africa east_africa north_africa southern_africa horn_of_africa mena emea
apac latam anz dach iberia levant maghreb siberia patagonia mediterranean pacific atlantic
arctic indian_ocean silicon_valley bay_area new_england midwest pacific_northwest deep_south
sun_belt rust_belt tri-state_area west_coast east_coast gulf_coast great_lakes rocky_mountains
alabama alaska arizona arkansas california colorado connecticut delaware florida hawaii idaho
illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota
mississippi missouri montana nebraska nevada new_hampshire new_jersey new new_york
north_carolina north_dakota ohio oklahoma oregon pennsylvania rhode_island south_carolina
south_dakota tennessee texas utah vermont virginia washington west wisconsin wyoming
district_of_columbia alberta british_columbia manitoba new_brunswick newfoundland nova_scotia
ontario prince_edward_island quebec saskatchewan yukon nunavut northwest_territories
new_south_wales queensland victoria tasmania western south northern_territory
australian_capital_territory andhra_pradesh arunachal_pradesh assam bihar chhattisgarh goa
gujarat haryana himachal_pradesh jharkhand karnataka kerala madhya_pradesh maharashtra manipur
meghalaya mizoram nagaland odisha orissa punjab rajasthan sikkim tamil_nadu telangana tripura
uttar_pradesh uttarakhand west_bengal jammu_and_kashmir kashmir ladakh puducherry
andaman_and_nicobar_islands lakshadweep anhui fujian gansu guangdong guangxi guizhou hainan
hebei heilongjiang henan hubei hunan jiangsu jiangxi jilin liaoning inner_mongolia ningxia
qinghai shaanxi shandong shanxi sichuan tibet xinjiang yunnan zhejiang baden-wurttemberg bavaria
bayern brandenburg hesse hessen lower_saxony mecklenburg-vorpommern north_rhine-westphalia
rhineland-palatinate saarland saxony saxony-anhalt schleswig-holstein thuringia acre alagoas
amapa amazonas bahia ceara espirito_santo goias maranhao mato_grosso mato_grosso_do_sul
minas_gerais para paraiba parana pernambuco piaui rio_grande_do_norte rio_grande_do_sul rondonia
roraima santa_catarina sao_paulo sergipe tocantins aguascalientes baja baja_california_sur
campeche chiapas chihuahua coahuila colima durango guanajuato guerrero hidalgo jalisco michoacan
morelos nayarit nuevo_leon oaxaca puebla queretaro quintana_roo san_luis_potosi sinaloa sonora
tabasco tamaulipas tlaxcala veracruz yucatan zacatecas andalusia andalucia aragon asturias
balearic_islands basque_country canary_islands cantabria castile castilla_y_leon
castilla-la_mancha catalonia catalunya extremadura galicia la_rioja murcia navarre valencia
abruzzo apulia puglia basilicata calabria campania emilia-romagna friuli lazio liguria lombardy
lombardia marche molise piedmont piemonte sardinia sicily tuscany toscana trentino umbria veneto
aosta_valley alsace aquitaine auvergne brittany bretagne burgundy champagne corsica
ile-de-france languedoc limousin lorraine normandy normandie occitanie picardy provence
rhone-alpes hauts-de-france grand_est nouvelle-aquitaine pays_de_la_loire centre-val_de_loire
flanders wallonia brussels-capital zeeland friesland groningen gelderland north_holland
south_holland utrecht limburg overijssel drenthe flevoland north_brabant tyrol carinthia styria
salzburg vorarlberg burgenland upper_austria lower_austria zurich bern ticino valais vaud geneva
graubunden lapland uusimaa scania skane jutland zealand funen cornwall devon dorset somerset
wiltshire hampshire kent sussex east_sussex west_sussex surrey essex suffolk norfolk
cambridgeshire hertfordshire bedfordshire buckinghamshire oxfordshire berkshire gloucestershire
herefordshire worcestershire warwickshire northamptonshire leicestershire nottinghamshire
derbyshire lincolnshire staffordshire shropshire cheshire lancashire yorkshire north_yorkshire
west_yorkshire south_yorkshire east_yorkshire merseyside greater_manchester west_midlands
east_midlands tyne_and_wear northumberland cumbria durham lothian highlands strathclyde fife
aberdeenshire greater_london home_counties east_anglia gauteng western_cape eastern_cape
kwazulu-natal free limpopo mpumalanga north_west northern_cape lagos rivers kano abuja oromia
amhara tigray nairobi mombasa rift_valley sindh khyber_pakhtunkhwa balochistan gilgit-baltistan
dhaka chittagong west_java east_java central_java bali sumatra java borneo sulawesi kalimantan
papua mindanao luzon visayas sabah sarawak johor selangor penang kedah perak pahang kelantan
terengganu negeri_sembilan malacca melaka hokkaido honshu kyushu shikoku okinawa kanto kansai
tohoku chubu chugoku gyeonggi jeju busan new_territories kowloon hong_kong_island dubai
abu_dhabi sharjah riyadh eastern
"""

CITIES = """
london paris berlin madrid rome lisbon dublin amsterdam brussels vienna prague budapest warsaw
stockholm oslo copenhagen helsinki reykjavik athens bucharest sofia belgrade zagreb ljubljana
bratislava vilnius riga tallinn kyiv kiev minsk moscow chisinau tbilisi yerevan baku ankara
istanbul nicosia valletta luxembourg_city monaco_city andorra_la_vella san_marino_city
vatican_city tirana skopje podgorica sarajevo pristina bern berne manchester birmingham leeds
liverpool sheffield bristol newcastle nottingham leicester coventry bradford hull
kingston_upon_hull stoke stoke-on-trent wolverhampton plymouth southampton portsmouth derby
swindon milton_keynes northampton luton norwich ipswich cambridge oxford brighton hove
bournemouth poole exeter gloucester cheltenham worcester hereford shrewsbury chester preston
blackpool blackburn bolton wigan warrington stockport oldham rochdale salford huddersfield
halifax wakefield doncaster rotherham barnsley york harrogate scarborough middlesbrough
sunderland gateshead durham carlisle lancaster lincoln peterborough chelmsford colchester
southend southend-on-sea basildon guildford woking crawley gatwick heathrow maidstone canterbury
dover folkestone ashford tunbridge_wells slough watford stevenage st_albans hemel_hempstead
high_wycombe aylesbury bedford cardiff swansea newport wrexham bangor aberystwyth edinburgh
glasgow aberdeen dundee inverness stirling perth belfast derry londonderry lisburn armagh cork
limerick galway waterford kilkenny wexford sligo drogheda dundalk athlone killarney hamburg
munich munchen cologne koln frankfurt stuttgart dusseldorf dortmund essen leipzig bremen dresden
hanover hannover nuremberg nurnberg duisburg bochum wuppertal bielefeld bonn munster karlsruhe
mannheim augsburg wiesbaden gelsenkirchen monchengladbach braunschweig kiel chemnitz aachen
halle magdeburg freiburg krefeld lubeck oberhausen erfurt mainz rostock kassel hagen potsdam
saarbrucken hamm ludwigshafen oldenburg osnabruck leverkusen heidelberg darmstadt solingen
regensburg ingolstadt wurzburg wolfsburg ulm heilbronn pforzheim gottingen bottrop trier
recklinghausen reutlingen bremerhaven koblenz jena erlangen siegen hildesheim salzgitter cottbus
gutersloh paderborn bamberg bayreuth konstanz passau landshut rosenheim kempten flensburg
wilhelmshaven schwerin weimar marseille lyon toulouse nice nantes strasbourg montpellier
bordeaux lille rennes reims le_havre saint-etienne toulon grenoble dijon angers nimes
villeurbanne clermont-ferrand le_mans aix-en-provence brest tours amiens limoges annecy
perpignan metz besancon orleans rouen mulhouse caen nancy argenteuil montreuil roubaix tourcoing
avignon poitiers cannes antibes la_rochelle calais dunkirk dunkerque pau bayonne biarritz
chambery versailles boulogne-billancourt saint-denis nanterre courbevoie la_defense colmar milan
milano naples napoli turin torino palermo genoa genova bologna florence firenze bari catania
venice venezia verona messina padua padova trieste taranto brescia parma prato modena
reggio_calabria reggio_emilia perugia livorno ravenna cagliari foggia rimini salerno ferrara
sassari latina monza syracuse siracusa bergamo pescara trento vicenza terni bolzano novara
piacenza ancona andria udine arezzo cesena lecce pisa como lucca siena sorrento amalfi capri
treviso barcelona seville sevilla zaragoza malaga murcia palma las_palmas bilbao alicante
cordoba valladolid vigo gijon hospitalet vitoria la_coruna a_coruna granada elche oviedo
badalona cartagena terrassa jerez sabadell mostoles santa_cruz pamplona almeria san_sebastian
donostia burgos santander castellon albacete getafe alcorcon logrono badajoz salamanca huelva
marbella leon tarragona cadiz lleida jaen ourense girona lugo caceres toledo segovia ibiza porto
braga coimbra funchal faro aveiro setubal amadora evora guimaraes viseu leiria rotterdam
the_hague den_haag utrecht eindhoven tilburg groningen almere breda nijmegen enschede haarlem
arnhem zaanstad amersfoort apeldoorn hertogenbosch den_bosch maastricht leiden dordrecht
zoetermeer zwolle delft deventer alkmaar venlo heerlen hilversum schiphol antwerp antwerpen
ghent gent charleroi liege bruges brugge namur leuven mons mechelen aalst kortrijk hasselt
ostend oostende zurich geneva basel lausanne winterthur lucerne luzern st_gallen lugano biel
thun zug fribourg neuchatel schaffhausen chur davos graz linz salzburg innsbruck klagenfurt
villach wels st_polten dornbirn gothenburg goteborg malmo uppsala vasteras orebro linkoping
helsingborg jonkoping norrkoping lund umea gavle boras sundsvall kiruna lulea bergen trondheim
stavanger drammen fredrikstad kristiansand tromso sandnes alesund bodo aarhus odense aalborg
esbjerg randers kolding horsens vejle roskilde espoo tampere vantaa oulu turku jyvaskyla lahti
kuopio pori joensuu lappeenranta krakow cracow lodz wroclaw poznan gdansk szczecin bydgoszcz
lublin katowice bialystok gdynia czestochowa radom sosnowiec torun kielce rzeszow gliwice zabrze
olsztyn bielsko-biala bytom opole zielona_gora sopot zakopane brno ostrava plzen pilsen liberec
olomouc ceske_budejovice hradec_kralove pardubice zlin karlovy_vary kosice presov zilina nitra
banska_bystrica trnava debrecen szeged miskolc pecs gyor nyiregyhaza kecskemet szekesfehervar
cluj-napoca cluj timisoara iasi constanta craiova brasov galati ploiesti oradea braila arad
pitesti sibiu bacau plovdiv varna burgas ruse stara_zagora pleven novi_sad nis kragujevac
subotica split rijeka osijek zadar dubrovnik pula maribor kaunas klaipeda siauliai daugavpils
tartu narva parnu kharkiv odesa odessa dnipro donetsk zaporizhzhia lviv kryvyi_rih mykolaiv
mariupol luhansk vinnytsia kherson poltava chernihiv cherkasy sumy zhytomyr saint_petersburg
st_petersburg novosibirsk yekaterinburg kazan nizhny_novgorod chelyabinsk samara omsk rostov
rostov-on-don ufa krasnoyarsk voronezh perm volgograd krasnodar saratov tyumen tolyatti izhevsk
barnaul ulyanovsk irkutsk khabarovsk yaroslavl vladivostok makhachkala tomsk orenburg kemerovo
novokuznetsk ryazan astrakhan naberezhnye_chelny penza lipetsk kirov cheboksary tula kaliningrad
kursk sochi murmansk gomel mogilev vitebsk grodno thessaloniki patras heraklion larissa volos
ioannina piraeus rhodes corfu izmir bursa antalya adana gaziantep konya mersin diyarbakir
kayseri eskisehir samsun denizli trabzon bodrum limassol larnaca paphos famagusta batumi kutaisi
gyumri ganja sumgait new_york_city nyc manhattan brooklyn queens bronx staten_island los_angeles
chicago houston phoenix philadelphia san_antonio san_diego dallas san_jose austin jacksonville
fort_worth columbus charlotte indianapolis san_francisco seattle denver nashville oklahoma_city
el_paso boston portland las_vegas detroit memphis louisville baltimore milwaukee albuquerque
tucson fresno sacramento mesa kansas_city atlanta omaha colorado_springs raleigh long_beach
virginia_beach miami oakland minneapolis tulsa bakersfield wichita arlington tampa new_orleans
cleveland honolulu anaheim lexington stockton corpus_christi henderson riverside newark
saint_paul st_paul santa_ana cincinnati irvine orlando pittsburgh st_louis saint_louis
greensboro jersey_city anchorage plano buffalo chandler chula_vista madison gilbert reno
fort_wayne north_las_vegas lubbock irving laredo winston-salem chesapeake glendale garland
scottsdale norfolk boise fremont spokane santa_clarita baton_rouge richmond hialeah
san_bernardino tacoma modesto huntsville des_moines yonkers rochester moreno_valley fontana
montgomery aurora akron little_rock shreveport augusta grand_rapids mobile salt_lake_city
tallahassee huntington_beach grand_prairie overland_park knoxville brownsville newport_news
santa_rosa chattanooga oceanside fort_lauderdale rancho_cucamonga port_st_lucie ontario
vancouver tempe springfield cape_coral pembroke_pines sioux_falls peoria elk_grove corona eugene
salem palmdale salinas pasadena rockford pomona hayward fort_collins joliet escondido torrance
bridgeport alexandria sunnyvale cary lakewood hollywood paterson naperville mcallen mesquite
dayton savannah clarksville orange fullerton killeen frisco hampton mckinney warren
west_valley_city columbia olathe sterling_heights new_haven miramar waco thousand_oaks
cedar_rapids charleston visalia topeka elizabeth gainesville thornton roseville carrollton
coral_springs stamford simi_valley concord hartford kent lafayette midland surprise denton
victorville evansville santa_clara abilene athens_georgia vallejo allentown norman beaumont
independence murfreesboro ann_arbor berkeley provo el_monte lansing fargo downey costa_mesa
wilmington arvada inglewood miami_gardens carlsbad westminster elgin west_jordan round_rock
clearwater waterbury gresham fairfield billings lowell san_buenaventura pueblo high_point
west_covina murrieta antioch temecula norwalk centennial everett palm_bay wichita_falls
green_bay daly_city burbank richardson pompano_beach north_charleston broken_arrow boulder
west_palm_beach santa_maria el_cajon davenport rialto las_cruces san_mateo lewisville south_bend
lakeland erie tyler pearland college_station kenosha sandy_springs clovis flint roanoke albany
jurupa_valley compton san_angelo hillsboro lawton renton vista davie greeley mission_viejo
dearborn south_gate tuscaloosa livonia new_bedford vacaville brockton roswell beaverton quincy
sparks yakima lee's_summit federal_way carson santa_monica hesperia allen rio_rancho yuma orem
lynn redding spokane_valley miami_beach league lawrence santa_barbara plantation sandy_city
sunrise macon longmont boca_raton san_marcos greenville waukegan fall_river chico newton
san_leandro reading fort_smith newport_beach asheville nashua edmond whittier nampa bloomington
deltona hawthorne duluth carmel suffolk clifton citrus_heights livermore tracy alhambra kirkland
trenton ogden hoover cicero fishers sugar_land danbury meridian indio menifee champaign
buena_park troy o'fallon redmond bellevue cupertino mountain_view palo_alto menlo_park
redwood_city foster_city san_rafael walnut_creek pleasanton napa sonoma monterey
carmel-by-the-sea malibu beverly_hills culver_city venice_beach el_segundo marina_del_rey
hoboken white_plains greenwich princeton ithaca schenectady poughkeepsie scranton harrisburg
bethlehem annapolis bethesda silver_spring rockville reston herndon tysons mclean fairfax
chapel_hill research_triangle charlottesville williamsburg myrtle_beach hilton_head st_augustine
key_west sarasota fort_myers daytona_beach pensacola destin biloxi gulfport jackson
bowling_green youngstown canton kalamazoo traverse saginaw oshkosh eau_claire bismarck sioux
council_bluffs cheyenne casper missoula bozeman helena coeur_d'alene olympia bellingham juneau
fairbanks hilo maui kauai oahu santa_fe taos flagstaff sedona palm_springs san_luis_obispo
lake_tahoe park moab aspen vail telluride jackson_hole toronto montreal calgary edmonton ottawa
winnipeg quebec_city hamilton kitchener victoria halifax_nova_scotia oshawa windsor saskatoon
regina st_catharines sherbrooke barrie kelowna abbotsford sudbury kingston saguenay
trois-rivieres guelph moncton thunder_bay saint_john st_john's waterloo brampton mississauga
markham vaughan surrey burnaby laval gatineau longueuil oakville burlington red_deer lethbridge
kamloops nanaimo fredericton charlottetown whitehorse yellowknife iqaluit banff whistler jasper
niagara_falls mexico_city ciudad_de guadalajara monterrey puebla tijuana juarez ciudad_juarez
zapopan merida cancun queretaro san_luis_potosi aguascalientes hermosillo saltillo mexicali
culiacan chihuahua morelia toluca acapulco veracruz oaxaca tampico durango mazatlan
puerto_vallarta los_cabos cabo_san_lucas ensenada reynosa matamoros nuevo_laredo villahermosa
tuxtla_gutierrez xalapa cuernavaca pachuca tepic colima guatemala_city san_salvador tegucigalpa
san_pedro_sula managua panama_city havana santo_domingo port-au-prince san_juan nassau
bridgetown port_of_spain montego_bay punta_cana sao_paulo rio_de_janeiro rio brasilia salvador
fortaleza belo_horizonte manaus curitiba recife porto_alegre belem goiania guarulhos campinas
sao_luis maceio natal teresina campo_grande joao_pessoa santo_andre osasco jaboatao sao_bernardo
uberlandia sorocaba contagem aracaju feira_de_santana cuiaba joinville juiz_de_fora londrina
niteroi ribeirao_preto florianopolis santos sao_jose_dos_campos maringa buenos_aires rosario
mendoza la_plata tucuman mar_del_plata salta neuquen bariloche ushuaia bahia_blanca
santiago_de_chile santiago valparaiso vina_del_mar concepcion antofagasta temuco la_serena
iquique puerto_montt punta_arenas lima arequipa trujillo chiclayo cusco cuzco piura iquitos
huancayo bogota medellin cali barranquilla cucuta bucaramanga pereira santa_marta manizales
caracas maracaibo valencia barquisimeto maracay quito guayaquil cuenca la_paz
santa_cruz_de_la_sierra cochabamba sucre el_alto asuncion montevideo punta_del_este georgetown
paramaribo cayenne cairo giza luxor aswan port_said suez sharm_el-sheikh hurghada casablanca
rabat marrakesh marrakech fes fez tangier agadir meknes oujda algiers oran constantine annaba
tunis sfax sousse tripoli benghazi misrata khartoum omdurman port_sudan juba addis_ababa
dire_dawa mekelle gondar bahir_dar asmara djibouti_city mogadishu hargeisa nairobi mombasa
kisumu nakuru eldoret kampala entebbe gulu kigali bujumbura dar_es_salaam dodoma arusha zanzibar
mwanza lusaka ndola kitwe harare bulawayo lilongwe blantyre maputo beira johannesburg cape_town
durban pretoria port_elizabeth gqeberha bloemfontein east_london pietermaritzburg soweto sandton
stellenbosch polokwane nelspruit kimberley windhoek gaborone maseru mbabane antananarivo
port_louis lagos abuja kano ibadan port_harcourt benin kaduna enugu onitsha aba ilorin jos warri
calabar owerri abeokuta uyo akure maiduguri sokoto zaria accra kumasi tamale takoradi tema
cape_coast abidjan yamoussoukro bouake dakar thies saint-louis bamako ouagadougou niamey conakry
freetown monrovia lome cotonou porto-novo banjul bissau nouakchott douala yaounde libreville
brazzaville kinshasa lubumbashi goma kisangani luanda huambo ndjamena bangui malabo sao_tome
praia riyadh jeddah mecca makkah medina madinah dammam khobar dhahran tabuk taif abha dubai
abu_dhabi sharjah ajman ras_al_khaimah fujairah al_ain doha manama muscat salalah kuwait_city
sanaa aden amman aqaba irbid zarqa beirut damascus aleppo homs latakia baghdad basra mosul erbil
sulaymaniyah najaf karbala kirkuk jerusalem tel_aviv haifa beersheba eilat ramallah gaza
nazareth netanya herzliya tehran mashhad isfahan karaj shiraz tabriz qom ahvaz kermanshah kerman
yazd rasht kabul kandahar herat mazar-i-sharif jalalabad karachi lahore faisalabad rawalpindi
gujranwala peshawar multan hyderabad islamabad quetta sialkot bahawalpur sargodha sukkur
abbottabad mumbai bombay delhi new_delhi bangalore bengaluru ahmedabad chennai madras kolkata
calcutta surat pune poona jaipur lucknow kanpur nagpur indore thane bhopal visakhapatnam vizag
pimpri-chinchwad patna vadodara baroda ghaziabad ludhiana agra nashik faridabad meerut rajkot
kalyan vasai-virar varanasi banaras srinagar aurangabad dhanbad amritsar navi_mumbai allahabad
prayagraj ranchi howrah coimbatore jabalpur gwalior vijayawada jodhpur madurai raipur kota
guwahati chandigarh solapur hubli dharwad tiruchirappalli trichy bareilly mysore mysuru tiruppur
gurgaon gurugram aligarh jalandhar bhubaneswar warangal guntur bhiwandi saharanpur gorakhpur
bikaner amravati noida jamshedpur bhilai cuttack firozabad kochi cochin ernakulam
thiruvananthapuram trivandrum kozhikode calicut thrissur kollam kannur bhavnagar dehradun
durgapur asansol nanded kolhapur ajmer gulbarga kalaburagi jamnagar ujjain loni siliguri jhansi
ulhasnagar jammu sangli mangalore mangaluru erode belgaum belagavi ambattur tirunelveli malegaon
gaya jalgaon udaipur maheshtala davanagere kurnool rajahmundry bokaro bellary patiala agartala
bhagalpur muzaffarnagar latur dhule tirupati rohtak korba bhilwara brahmapur muzaffarpur
ahmednagar mathura avadi kadapa rampur shimla gangtok imphal shillong aizawl kohima itanagar
panaji margao vasco pondicherry puducherry port_blair kavaratti silvassa daman diu leh manali
rishikesh haridwar nainital mussoorie darjeeling ooty kodaikanal munnar alleppey alappuzha hampi
pushkar jaisalmer mount_abu lonavala mahabaleshwar hinjewadi whitefield electronic_city
koramangala indiranagar andheri bandra powai worli lower_parel nariman_point bkc gachibowli
hitech_city madhapur kondapur salt_lake rajarhat new_town sector_v magarpatta kharadi hadapsar
baner wakad viman_nagar kalyani_nagar dwarka saket vasant_kunj connaught_place nehru_place okhla
cyber_city manesar sohna greater_noida omr guindy tidel_park sholinganallur perungudi velachery
adyar anna_nagar t_nagar dhaka chittagong chattogram khulna rajshahi sylhet rangpur barisal
comilla gazipur narayanganj mymensingh cox's_bazar kathmandu pokhara lalitpur bhaktapur
biratnagar thimphu paro colombo kandy galle jaffna negombo trincomalee male yangon rangoon
mandalay naypyidaw bangkok chiang_mai phuket pattaya hat_yai nakhon_ratchasima khon_kaen
udon_thani krabi koh_samui vientiane luang_prabang phnom_penh siem_reap sihanoukville hanoi
ho_chi_minh_city saigon da_nang haiphong hai_phong can_tho nha_trang hue vung_tau bien_hoa
da_lat kuala_lumpur george_town ipoh johor_bahru shah_alam petaling_jaya kota_kinabalu kuching
malacca klang seremban kuantan putrajaya cyberjaya subang_jaya jakarta surabaya bandung medan
semarang makassar palembang tangerang depok bekasi denpasar yogyakarta malang batam pekanbaru
padang balikpapan banjarmasin manado pontianak samarinda bogor solo surakarta manila quezon_city
davao cebu cebu_city makati taguig pasig zamboanga cagayan_de_oro antipolo iloilo bacolod baguio
general_santos tacloban caloocan singapore_city bandar_seri_begawan dili port_moresby beijing
shanghai guangzhou shenzhen chongqing tianjin chengdu wuhan xi'an xian hangzhou nanjing shenyang
harbin suzhou zhengzhou jinan qingdao dalian changsha kunming fuzhou xiamen ningbo hefei nanning
changchun shijiazhuang taiyuan nanchang guiyang urumqi lanzhou hohhot yinchuan xining lhasa
haikou sanya dongguan foshan wuxi changzhou zhuhai shantou wenzhou quanzhou yantai weifang
tangshan baotou luoyang datong kaifeng guilin yangzhou zhongshan huizhou jiangmen nantong xuzhou
yancheng hong_kong_city victoria_harbour central_hong_kong tsim_sha_tsui macau_city taipei
kaohsiung taichung tainan hsinchu taoyuan keelung tokyo yokohama osaka nagoya sapporo fukuoka
kobe kawasaki kyoto saitama hiroshima sendai chiba kitakyushu sakai niigata hamamatsu kumamoto
sagamihara shizuoka okayama kagoshima hachioji funabashi utsunomiya matsuyama higashiosaka
kanazawa nagano nara naha nagasaki toyota himeji gifu takamatsu akita aomori morioka yamagata
fukushima mito maebashi kofu tsu otsu wakayama tottori matsue tokushima oita miyazaki saga
yokosuka tsukuba narita haneda roppongi shinjuku shibuya ginza akihabara seoul busan incheon
daegu daejeon gwangju ulsan suwon changwon seongnam goyang yongin bucheon cheongju jeonju ansan
cheonan pohang gimhae jeju_city sejong pyongyang hamhung chongjin kaesong ulaanbaatar almaty
astana nur-sultan shymkent karaganda aktobe tashkent samarkand bukhara namangan andijan bishkek
osh dushanbe khujand ashgabat sydney melbourne brisbane adelaide gold_coast canberra wollongong
hobart geelong townsville cairns darwin toowoomba ballarat bendigo launceston mackay rockhampton
bunbury bundaberg wagga_wagga mildura alice_springs sunshine_coast parramatta auckland
wellington christchurch tauranga dunedin palmerston_north napier nelson rotorua queenstown
invercargill whangarei suva nadi apia nuku'alofa port_vila honiara noumea papeete
"""

AMBIGUOUS = """
aurora phoenix mobile reading nice bath split orange victoria florence jordan georgia chad
austin charlotte eugene lincoln hamilton jackson columbia troy salem independence concord
richmond madison washington chester warren carmel allen tyler norman lawrence quincy gilbert
chandler henderson elizabeth arlington springfield fairfield burlington kingston preston
halifax derby lafayette reno peoria murray clifton sterling sydney regina nelson victoria
salvador natal vitoria la_paz nancy angers tours pau mons hull dover bolton cork lucerne
como aba jos kota gaya male paro nara saga orem ogden sparks vista miramar sunrise edmond
hoover tracy meridian everett carson yuma joliet elgin pueblo casper helena billings jasper
whistler laval surrey sun_belt para acre leon granada santa_cruz santa_fe durango guerrero
hidalgo colima limburg zeeland java bali papua gulf pacific atlantic arctic levant
marion
"""

TOWNS = """
abingdon accrington aldershot altrincham andover ashby barnstaple barrow basingstoke bedworth
beverley bexhill bicester bideford bognor_regis bootle boston bracknell braintree bridgend
bridgwater burnley burton bury buxton camberley cannock chatham chippenham chorley cirencester
clacton crewe crosby darlington dartford daventry dewsbury didcot doncaster dorchester dudley
dunstable eastbourne eastleigh ellesmere_port epsom esher evesham falmouth fareham farnborough
farnham felixstowe gainsborough gillingham glossop gosport grantham gravesend grimsby halesowen
harlow harpenden hartlepool hastings havant hereford hinckley hitchin horsham huntingdon
ilkeston kettering kidderminster kings_lynn knutsford leamington leighton_buzzard letchworth
lewes lichfield loughborough lowestoft macclesfield maidenhead mansfield margate
market_harborough matlock melton_mowbray morecambe newbury newark newmarket newquay northwich
nuneaton ormskirk penzance pontefract redditch reigate rugby runcorn ryde salisbury sevenoaks
skegness solihull southport spalding stafford stamford stevenage stourbridge stratford-upon-avon
stroud sutton sutton_coldfield tamworth taunton telford tewkesbury thetford torquay truro
twickenham walsall wallasey wellingborough west_bromwich weston-super-mare weymouth whitby
whitehaven widnes winchester windsor wisbech witney wokingham worthing yeovil croydon wembley
ealing hounslow harrow enfield barnet bromley lewisham greenwich hackney islington camden
westminster kensington chelsea hammersmith fulham wandsworth lambeth southwark tower_hamlets
canary_wharf stratford shoreditch richmond livingston falkirk paisley kilmarnock ayr dumfries
elgin fort_william oban st_andrews kirkcaldy dunfermline motherwell hamilton cumbernauld
llandudno rhyl carmarthen pembroke merthyr_tydfil caerphilly pontypridd barry newry enniskillen
omagh coleraine ballymena portadown navan naas bray tralee ennis letterkenny castlebar mullingar
tullamore carlow portlaoise altona bad_homburg baden-baden bad_nauheim boblingen celle cuxhaven
delmenhorst dessau detmold duren eisenach emden eschborn esslingen fulda gera giessen goslar
hameln hanau herne hof iserlohn kaiserslautern kaufbeuren lingen luneburg marburg memmingen
minden moers neuss neubrandenburg neumunster offenbach offenburg peine plauen ratingen remscheid
rheine ruesselsheim sankt_augustin schweinfurt sindelfingen soest speyer stralsund suhl tubingen
unna villingen weiden wetzlar witten worms zwickau walldorf herzogenaurach garmisch
berchtesgaden abbeville agen ajaccio albi alencon arles arras auxerre bastia beauvais belfort
bergerac beziers blois bourges brive carcassonne chalon chartres chateauroux cherbourg cholet
compiegne evreux frejus gap la_roche-sur-yon laval le_puy lorient macon montauban montlucon
narbonne nevers niort perigueux quimper roanne rodez saint-brieuc saint-malo saint-nazaire
saint-quentin saint-tropez sete tarbes troyes valence valenciennes vannes vichy chamonix megeve
deauville honfleur lourdes sophia_antipolis agrigento alessandria asti avellino barletta belluno
benevento biella brindisi caserta catanzaro cosenza cremona crotone cuneo enna fiumicino
frosinone gorizia grosseto imperia isernia l'aquila la_spezia lodi macerata mantua mantova massa
matera nuoro oristano pavia pesaro pistoia pordenone potenza ragusa rovigo savona sondrio teramo
trapani varese vercelli viterbo portofino positano taormina cortina albacete alcala_de_henares
algeciras aviles benidorm cuenca el_puerto ferrol fuengirola gandia guadalajara huesca irun
linares lorca manresa mataro merida mollet palencia ponferrada reus sagunto soria talavera
teruel torrejon torrevieja zamora estepona nerja ronda sitges figueres almada barreiro cascais
sintra oeiras odivelas loures matosinhos gaia vila_nova_de_gaia portimao lagos albufeira tavira
estoril alphen amstelveen assen bergen_op_zoom capelle den_helder ede emmen gouda harderwijk
heerenveen helmond hoofddorp hoorn kampen katwijk lelystad middelburg nieuwegein oss purmerend
roermond roosendaal schiedam sittard spijkenisse veenendaal vlaardingen waalwijk weert zaandam
zeist zutphen wageningen aalst genk geel herentals ieper knokke lier lokeren ninove roeselare
sint-niklaas tienen turnhout vilvoorde waregem waterloo wavre zaventem louvain-la-neuve aarau
baden bellinzona frauenfeld glarus herisau kreuzlingen liestal locarno montreux nyon olten
rapperswil sion solothurn uster vevey wil yverdon zermatt st_moritz interlaken grindelwald
bregenz eisenstadt feldkirch kufstein leoben steyr wiener_neustadt kitzbuhel borlange eskilstuna
falun halmstad kalmar karlskrona karlstad kristianstad nykoping ostersund skelleftea sodertalje
trollhattan uddevalla varberg vaxjo visby arendal bodo gjovik hamar harstad haugesund kongsberg
larvik lillehammer molde moss narvik porsgrunn sarpsborg skien steinkjer fredericia
frederikshavn haderslev helsingor herning hillerod holstebro naestved nyborg silkeborg skive
slagelse sonderborg svendborg thisted viborg billund hameenlinna hyvinkaa kajaani kokkola kotka
kouvola mikkeli porvoo raahe rauma rovaniemi salo savonlinna seinajoki vaasa elblag gorzow
gniezno jelenia_gora kalisz konin koszalin legnica leszno lomza nowy_sacz piotrkow plock
przemysl slupsk suwalki tarnow tychy walbrzych wloclawek zamosc ceske_lipa chomutov decin
frydek-mistek havirov jihlava karvina kladno most opava prostejov prerov teplice trinec
usti_nad_labem banska_stiavnica martin poprad piestany trencin dunaujvaros eger kaposvar
nagykanizsa sopron szolnok szombathely tatabanya veszprem zalaegerszeg alba_iulia baia_mare
bistrita botosani buzau deva drobeta focsani giurgiu hunedoara piatra_neamt ramnicu_valcea
resita satu_mare slatina suceava targoviste targu_mures tulcea vaslui zalau asenovgrad
blagoevgrad dobrich gabrovo haskovo kardzhali kyustendil lovech montana pazardzhik pernik shumen
silistra sliven smolyan targovishte veliko_tarnovo vidin vratsa yambol cacak kraljevo krusevac
leskovac pancevo smederevo sombor zrenjanin karlovac sibenik slavonski_brod varazdin
velika_gorica vukovar celje koper kranj novo_mesto bitola kumanovo ohrid prilep tetovo durres
elbasan shkoder vlore korce fier banja_luka mostar tuzla zenica bijeljina niksic budva kotor
herceg_novi bar balti tiraspol bender cahul akhaltsikhe gori poti rustavi zugdidi vanadzor
alanya amasya aydin balikesir batman bolu canakkale corum edirne elazig erzurum fethiye giresun
hatay isparta iskenderun kahramanmaras karaman kastamonu kirikkale kirsehir kocaeli izmit
kutahya malatya manisa mardin marmaris mugla nevsehir ordu osmaniye rize sakarya sanliurfa siirt
sivas tekirdag tokat usak van yalova yozgat zonguldak cappadocia kusadasi cesme
americas uk us
"""
