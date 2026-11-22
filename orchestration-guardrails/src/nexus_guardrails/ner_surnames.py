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

"""Surnames for PII detection (data only, casefolded, packed; ``_`` stands for a space).

``PACKED``: surnames from South Asian, East and Southeast Asian, African, Arabic, Persian,
Turkish, European, Slavic, Jewish and Latin American traditions: a capitalised word before one
of these is taken as a given name ("Tanvir Ahmed"). ``WEAK`` surnames are also ordinary words
("Stone", "Bell"): they complete a name only after a known given name.
"""

from __future__ import annotations

# Surnames that are not ordinary words.
PACKED = """
abad abbas abbasi abboud abdallah abdel abdelaziz abdelhamid abdelnour abdelrahman abdi abdulla
abdullah abdullahi abe abebe abella abera abeysekera abeywardena abidi ablordey aboud abouelnaga
abraham abramov abreu abshir abu_bakr abu_zeid abubakar acar acaye acharya acheampong acosta acuna
adam adamczyk adams adamu adan addo adebayo adeleke aden adeniyi adeoye adesanya adewale adeyemi
adhikari adjei adjovi admasu adomako adu afanasyev afful afolabi afrah afrifa agarwal agbayani
agbeko agbo agbodjan aggarwal agrawal agu aguiar aguilar aguirre agyeman agyemang ahidjo ahluwalia
ahmad ahmadi ahmed ahn ahonen ahoua ahuja aigner aiyer ajayi akakpo akbari akello akhand akhtar
akhter akimov akintola akinwumi akoto akpa aksenov aksoy aktas akter akuffo akufo-addo al-ahmad
al-ali al-amin al-anazi al-ansari al-attiyah al-azzawi al-baghdadi al-bakr al-balushi al-banna
al-busaidi al-darwish al-dhaheri al-dosari al-farsi al-fayed al-ghamdi al-hajri al-hamadi al-harbi
al-harthy al-hashimi al-hinai al-hussein al-jaber al-jabri al-kaabi al-ketbi al-khalifa al-khatib
al-kuwaiti al-kuwari al-lawati al-maamari al-mahmoud al-maktoum al-mansouri al-marri al-masri
al-mazrouei al-mutairi al-nahyan al-naimi al-nuaimi al-omari al-otaibi al-qahtani al-qasimi
al-rasheed al-rashid al-rashidi al-rawahi al-sabah al-said al-saud al-sayed al-shammari al-shamsi
al-shehri al-siyabi al-subaie al-sulaiti al-suwaidi al-tamimi al-thani al-wahaibi al-yami al-zahawi
al-zahrani alabi alam alanazi alansari alaoui albrecht albu alcantara aldosari alejandro alekseev
alemu alexander alexandrov alexiou alfarsi alghamdi alharbi ali aliyu allen almansouri almeida
almutairi alonso alotaibi alqahtani alshammari alshehri alsubaie alvarado alvarez alves alzahrani
amani amarasekara amarasinghe amato ambaw amegah amer amini amoah amongi amoussou amouzou amponsah
amr amundsen anagnostou anand anani andersen anderson andersson ando andrada andrade andre
andreassen andreev andrei andresen andrews anena ang angeles anghel anisimov ankrah annan annor
ansah ansari antonio antoniou antonov antwi antônio anyanwu aoki apaza appiah aquilino aquino arai
araneda arango araujo aravena araya araújo ardeleanu arellano arias arkhipov armstrong arnaud
arnold arora arroyo arslan arthur arvidsson asadi asamoah asante asare asfaw ashraf asiedu aslam
aslan assefa athanasiou atienza atim attanayake atwal au aubert aubry aulakh auma austin avila
avraham avram awale awasthi aweys awil awolowo awuor axelsson ayala ayana aydin ayieko ayodele
ayoub azevedo azikiwe aziz azizi azulay azzam baah babatunde babic bacani badawi badu baek bagheri
bahrami bai baidoo baig bailly bains bajaj bajwa bak bakare bakke bakken bakker bakr bala balagtas
balan balasubramanian balasuriya balde baldwin balogh balogun baloyi bamba banda bandara banerjee
bangura bankole banks bansal banzon bar-lev bar-on baracol barakat baran baranov barasa barbier
barbieri barbosa barbu barnard barnes barnett barre barrera barrett barretto barrios barros barry
bartos bashir basile basnet basu bates batista battaglia bauer baumann baumgartner bautista beasley
becker bedi bediako bedie bedoya befekadu begum behzadi bekele belay belkacem bellini bello
bellucci belmonte belousov belov belyaev ben ben-ami ben-david ben-haim ben-yosef benali benamar
benchekroun benedetti benes beneš bengtsson benitez benjelloun bennani bennett benoit bensaid
benson bento benzema berge berger berglund bergman bergmann bergstrom berhanu bermudez bernardi
bernardo bertin bertrand besson bester bett bevan bezabih bezerra bhagat bhai bhalla bhandari
bhardwaj bhargava bhatia bhatnagar bhatt bhattacharjee bhattacharya bhattarai bhatti bhengu bhosale
bhuiyan bhullar bianchi biko bilgin bilic bindra birhanu biro biryukov bishara bisht biswas biton
biwott bizimana bjork bjorklund björk bjørk blair blanchard blanco blazek blazevic blom blomqvist
boateng bogado bogdan bogdanov bohm bondar bondarenko bonetti boni bonifacio bonnet bonsu borges
borisov borkowski bos bose bosman botero botha bouazizi bouchard boucher boudiaf boumediene
bourgeois boutros bouvier bouwman bouzid bowen bowman boyd boyko bozic bozkurt bradley brandt brar
braun bravo brennan brenner breton brewer brooks brouwer brun brunet bruni brunner bruno bryant
buchanan bucur buenaventura bui bulut burns busch busia bustos buthelezi bykov byrd byrne byun böhm
bùi caballero cabdi cabello cabral cabrera caceres cai cakir calderon caldwell cali callisaya calvo
camara cameron campbell campos cano cao capistrano caputo carandang carbone cardenas cardona
cardoso cardozo carlson carmona caron carpentier carrasco carre carrillo carroll carter caruso
carvajal carvalho castillo castro catapang cattaneo cavalcanti cayetano cazacu ccori cech ceesay
cele celik cermak cerny cervantes cetin chacko chacon chadha chae chahine chakrabarti chakraborty
chambers chambi chan chand chanda chandler chandra chandrasekhar chang chaoui charles charpentier
chatterjee chaturvedi chau chaudhary chaudhry chauhan chauke chavan chavez chavula chawla cheboi
cheema chehab chen cheng cheon chepkwony cherian cherif chernov chernyshev cheruiyot cheung
chevalier chiba chigumba chikaonda chikwanha chilufya chimbwanda chimombe chinamasa chinwe chirwa
chisanga chishti chiu chiweshe chmielewski cho choi chong chopra choque choudhary chowdhury
christensen christiansen christodoulou chu chua chukwu chukwuma cifuentes ciobanu cipriani cisse
claes claesson clarke clement coelho coetzee cohen cojocaru coleman colin collet collin colombo
colque conceição concepcion condori conradie constantin constantinou conteh conti contreras cooray
coppola cordeiro coronel correia cortes cortez coskun costa coulibaly craig crawford crespo cristea
cronje cruz cui cumar cummings cunha cunningham curtis cwele d'costa d'silva d'souza da_costa
da_cruz da_rocha da_silva dabrowski dacanay dagne dago dahal dahan daher dahir dahl dai dalisay
damico daniel daniels danielsson danilov danjuma dankwa danquah dantata darko darwish das dasgupta
datta datu david davidson davies davis davydov dawson dcosta de_almeida de_angelis de_assis
de_backer de_beauvoir de_beer de_boer de_bruijn de_bruin de_carvalho de_freitas de_gaulle de_graaf
de_groot de_guzman de_haan de_jesus de_jong de_klerk de_la_croix de_la_cruz de_la_fontaine
de_la_fuente de_la_rosa de_la_torre de_la_vega de_leon de_lima de_los_rios de_los_santos de_luca
de_mel de_melo de_oliveira de_paula de_santis de_silva de_smedt de_sousa de_souza de_vera
de_villiers de_vries de_wet de_wit de_zoysa declercq dekker del_castillo del_mundo del_pozo del_rio
del_rosario del_río del_valle dela_cruz dela_rosa deleon delgado delos_santos demetriou demir
demissie deng denis denisov dennis deresse des_jardins desai deschamps deshmukh deshpande desmet
desta devi dey dhawan dhillon diaconu diallo dias diaz diep dietrich diez dijk dijkstra dima
dimaculangan dimitriou dinh dinu diop dirie diriye dissanayake dixit dixon dizon dje djebbar
djordjevic dladla dlamini dmitriev do_nascimento doan dobre dogan dogbe doherty dolezal doležal
dolo domingo domingues dominguez donati dorje dorji dos_santos dosanjh dossou douglas doumbia doyle
doğan dragomir drogba dsilva dsouza du du_bois du_plessis du_pont du_toit duale duan duarte dube
dubey dubois duda dudek dufour duggal duman dumas dumitru dumont duncan dunn duodu duong duplessis
dupond dupont dupuis dupuy duran durand durrani dutta duval dvorak dvořák dwivedi dyantyi dzifa
díaz dąbrowski dương eapen ebrahimi echeverri economou eder edirisinghe edwards efimov efremov egal
egger egorov eid eide ekanayake el-baz el-gendy el-hassan el-kady el-khoury el-masry el-sayed
el-shamy el-sherif el_amrani el_fassi el_idrissi elbaz elgendy elhassan eliasson elkady elkhoury
elliott ellis elmasri elmi elnahas elsayed elshamy elsherif emelyanov emenike endo ene engel
engelbrecht engstrom enriquez eom epstein erasmus ercan erdogan eremin eren erickson eriksen
eriksson ermakov escudero esfahani esguerra eshetu espinosa espinoza espiritu esposito esteban
esteves estrada eto'o etoo evangelista evans eyadema eze ezeh fabbri fabre fagbemi fahmy fajardo
fantahun farag farah farahani faraji fard farias farina farkas farooqi farooqui farrell farsi
fasanya fashola fassi faure fawzy faye fazeli fedorov fedotov feher fehér fekete feng ferguson
fernandes fernandez fernando fernández ferrara ferrari ferraro ferreira ferrer ferri fiala fields
figueroa fikre filatov filip filippov fiore fischer fitzgerald fitzpatrick fleming fleury flomo
florea flores flynn fomin fon fonseca fonseka fontaine fontana fonyuy forsberg foster fosu fouad
fourie fournier francis franco francois franke franklin fransson fraser frazier frederiksen
fredriksen fredriksson freitas friedman friedrich frimpong frolov fuchs fuentes fujii fujimoto
fujita fujiwara fukuda fung furukawa gabay gaber gaikwad gaillard galang galanis galkin gallagher
gallardo gallego galli gallo gamage gamal gambo gandhi ganguly gao garba garcia garcía gardner garg
garnier garrett garrido garza gashaw gassama gatchalian gathogo gatti gautam gauthier gautier
gaviria gavrilov gawde gbadamosi gbagbo gbaguidi gcabashe gebre gebremariam gebrselassie gedi
geleta gemechu george georgescu georgiou georgopoulos gerard gerasimov germain geronimo gerritsen
getachew ghali ghanem ghasemi gheorghe ghimire ghorbani ghosh gibson gil gilani gill gimenez
giordano giraldo girard giraud girma gitau githinji giuliani gnahore gnassingbe godage godoy goh
gok goldberg goldman goldstein golob golubev gomes gomez goncalves goncharov gondwe gonzales
gonzalez gonzález gonçalves goodwin goossens gopal gorbunov gordon gori gorshkov gorski goto
govindarajan gowda goyal gqirana grabowski grachev graf grasso graves greco greene gregory grewal
grgic griffith griffiths grigoriev grishin grobler groen gromov grover gruber gu guei guerin guerra
guerrero guerrouj guevara gueye guha guidi guillaume guillot guimaraes guimarães guled guler gulyas
gulyás gumbo gumede gunaratne gunawardena gunawardene gundersen gunes gunn gunnarsson gunther guo
gupta gurung gusev gustafsson gutierrez guyot guzman gwak gyamfi gyan gyasi gómez güler güneş
günther haas habib habibi habimana hadad haddad haddadin hadebe hafez hagen hahn haile hailemariam
hajek hakansson hakim hakizimana halabi halvorsen hamad hamalainen hamdan hamed hamid hamidi
hamilton hamunyanga han hani hanna hansen hanson hansson haque hara harada hariharan harmon harper
harris harrison hartmann haruna harvey hasegawa hashemi hashi hashimoto hashmi hassan hauge haugen
havyarimana hawkins hayashi hayat hayes haynes hedlund hegde heidari heikkila heikkinen heinonen
heinrich henao henderson hendriks heng henriksen henriksson henriques henry heo herath hermans
hernandes hernandez hernández herrera herrero herrmann hersi herve hicks hidalgo higa higgins
hijazi hirano hirsi hlongwane hlungwani ho hoang hoarau hoekstra hofer hoffman hoffmann hofmann
holland holmberg holmes hopkins hoque horak horowitz horton horvat horvath horvát horák hoshino
hosni hosny hossain hossein hosseini hosseinzadeh hou houngbo hounkpatin howard howell howells
hoàng hribar hrytsenko hu huaman huanca huang hubbard huber hubert hudson huet hughes hui huisman
humphreys hundal hunter huq hussain hussein husseini hutchinson huynh huỳnh hwang hyun hájek
håkansson høgh iancu ibanez ibrahim idris idrissi ige iglesias ignacio igwe ikeda ikenna ilic ilie
ilić ilori ilyin im imai inca innes inoue ioannou ionescu iordache ip irie isaev isaksson ishida
ishii ishikawa isik islam ismail issa isse ito ivanov ivanova iversen iwasaki iwata iwuchukwu
iyengar iyer izquierdo işık jabbour jaber jablonski jacinto jackson jacob jacobs jacobsen jacquet
jadhav jafari jafri jain jakab jakobsen jakobsson jakubowski jalali jali jalloh jallow james jammeh
jang jankovic jankowski jansen janssen janssens jansson jaramillo jarvinen jasinski javed javier
jawara jaworski jayakody jayasekara jayasuriya jayatilleke jayawardena jayawardene jelinek jenkins
jennings jensen jeon jeong jeppesen jere jha jhunjhunwala ji jia jiang jibril jimenez jiménez jin
jindal johal johannessen johansen johansson john johnsen johnson johnston jokinen joly jonas jones
jonsson joo jordan jorgensen joseph joshi josé joubert jovanovic jovanović jovic joão juarez juhasz
juhász julien juma jung juric jutt jäger jørgensen kachale kacou kaczmarczyk kaczmarek kadam kadlec
kagame kahraman kaimal kaiser kakkar kalinin kalinowski kalogeropoulos kalou kalua kam kamal kamali
kamande kamanga kamara kamath kamau kamel kaminski kamiński kamwana kamwendo kanaan kandasamy
kandil kaneko kang kang'ethe kannan kante kanu kapambwe kapito kaplan kapoor kapur kara karaca
karagiannis karam karamanlis karami karanja kareem kargbo karim karimi kariuki karjalainen karki
karlsen karlsson karnga karpov karunanayake karunaratne kassa kassab kassem kasyoka kato katona
kattan katz katzenberg kaunda kaur kavanagh kawano kawasaki kaya kayani kayondo kazakov kazemi
kazmi keane kearney kebede keegan keinan keita keller kelley kelly kemboi kennedy kente kerr keskin
kessler khadka khalaf khalid khalifa khalil khan khandelwal khanna khanyile kharitonov khatun
khawaja khondaker khosa khosravi khoury khumalo khurana kibaki kibet kikuchi kilic kilonzo kim
kimani kimura kimutai kini kinnunen kinoshita kinuthia kinyanjui kioko kipchoge kipkemboi kiplagat
kiplimo kiprop kiprotich kipruto kiptanui kiptoo kirillov kirui kiselev kiwanuka kizito klein
klimov klymenko knezevic knudsen knutsen knyazev kobayashi koc kocak koch kodikara kodjo koech
koffi koh kohler kohli kohn koirala kojima kok kokkinos kolar kolesnikov kollie kolodziej komarov
komatsu komen komolafe konan konate kondo kondratiev kone konecny kong konig konovalov konstantinou
koo korhonen korir korkmaz korolev koroma korosec kosgei koshy koskinen koster kotov kouadio kouame
kourouma kovac kovacevic kovacic kovacs koval kovalchuk kovalenko kovalev kovalskyi kovar kovačević
kovács kowalczyk kowalski kozlov kozlowski kozłowski koç kpade kpoto krajnc kramer krasnov
kratochvil kraus krause kravchenko kravets krawczyk krishna krishnamurthy krishnan kristensen
kristiansen kristoffersen kriz krol kruger krylov král król krüger kubiak kubo kucera kucharski
kudo kudryavtsev kufuor kuhn kuipers kulikov kulkarni kuma kumar kumaran kumarasinghe kumi kumwenda
kunene kurian kuroda kurosawa kurt kurup kuzmenko kuzmin kuznetsov kučera kwarteng kwek kwiatkowski
kwok kwon kyalo köhler kılıç la_fontaine la_rue labuschagne lacroix lagat lagos lahlou lahtinen
laine laitinen lakatos lakwena lal lam lama lambrou lamont lang langa langat lange langlois lara
larsen larson larsson latif latifi lau laubscher laurent laursen lawal lawan lawlor lawrence lawson
lazar lazarev lazic lazo le le_blanc le_brun le_clerc le_gall le_goff le_pen le_roux le_roy lebedev
leblanc leblond leclerc leclercq leclere lecomte lee lefebvre lefevre legall legaspi leger legesse
legrand lehmann lehtinen lehtonen leite leitner leiva lemaire lemaitre lemma lemoine leon leonard
leone leong leonov leroux leroy leslie leung leveque levi lewandowski lhamo li liang liao liban
lieberman liew lim lima limann limbu lin lind lindberg lindgren lindqvist lindstrom lindström
lipschitz liu liyanage llewellyn lloyd lodhi lofgren loginov loh lok lombardi lombardo londono
longo lopes lopez lorenz lorenzo lotfy louis louw lowe lozano lu lubega lucas ludwig lukacs
lukyanov lukács lund lundberg lunde lundgren lundin lundqvist lundstrom lungu luo luong luthra
lwanga lyons lysenko lê lópez lööf lý maalouf maan maas mabasa mabaso mabunda mac_donald macapagal
macaraeg macdonald macgregor machado macharia maciejewski macintosh mackay mackenzie maclean
macleod macmillan madikizela madsen madushanka maeda maes magagula magalhaes magalhães magar magno
magnusson magsaysay maguire magut magwaza mahad mahajan mahama mahamud mahdavi maheshwari mahfouz
mahlangu mahmoud mahmud mahony mai maia maier maillard maina majewski majumdar majumder mak makarov
makela makhanya makinde makinen makokha makris maksimov maktoum malabanan malan maldonado maleki
malhotra malik malinowski malka maltsev maluleke malyshev mamani manalo manansala mancini mandel
mandela mann manole mansaray mansour mansouri manu mapfumo marais marasigan marcelo marchand
marchenko marchetti marciniak marek margolis mariani mariano maric marie marin marino maritim
maritz markov markovic marković marques marquez marras marshall martinelli martinez martini martins
martinsen martinsson marty martynov martínez maruyama mascarenhas maseko mashingaidze masinde
maslov masri massaquoi masson masuda masuku matar matei matejka mathe mathebula mathew mathieu
mathisen mathonsi mathur matic matos matshoba matsuda matsui matsumoto matsuo matthews mattila
mattsson maturana matveev matviienko mavros mavuso maxamed maxamud mayer mayr mazibuko mazur
mazurek mazza mbarga mbatha mbaye mbeki mbewe mbugua mbuli mburu mc_donald mc_gregor mcauliffe
mcbride mccabe mccann mccarthy mccoy mcdaniel mcdermott mcdonald mcgee mcgrath mcgregor mchugh
mchunu mcintyre mckay mckenna mckinney mclaughlin mcleod mcmahon mcmillan mcnamara mcneil mcpherson
mcrae mdingi mdluli medeiros medina medvedev meehan mehdizadeh mehmood mehra mehta meier meijer
mejia mekki mekonnen mekuria melaku mello melnikov melnyk melo memon menard mendes mendez mendis
mendoza menezes mengistu menon mensah mercado mercier meredith merino mersha mertens messaoudi
messina meszaros metwally meunier meyer meyerson mhango mhatre mhlanga mhlongo mia miah michailidis
michalak michalski michel mihai mikhael mikhailov mikheev mikkelsen miles milic mills milosevic
milovanovic milošević minhas mintah miranda mironov mirza mirzaei mishra misra mitchell mitra
mitrofanov mitrovic mittal miura miyagi miyake miyamoto miyazaki mizrahi mizuno mkandawire mkhize
mkhwanazi mlakar mlambo mlilo mncube mngadi modi moe moen mohamed mohammad mohammadi mohammed
mohamud mohan mohseni moiseev mok mokoena mokwena moldovan molefe molina mollah moller molnar
molnár moloi moloney monaghan mondal mondol monteiro montero montgomery monti montoya moorthy
moradi moraes morales moran moreau moreira morelli moreno moretti mori moriarty morita moroz
morozov morrison morsi mortensen moser mosia mosop mostafa motaung motsepe moulin moura mourad
mousa mousavi moussa moya mphahlele mpofu mqhayi mridha msimang msiska msomi mtambo mthembu
mthethwa mtshali mubanga mubarak muchiri mudau mudzuri mueller mugabe mugabi mugisha mugo muhammadu
muigai mukamana mukamuri mukandoli mukasa mukherjee mukhin mukhopadhyay mukhwana mulaudzi mulcahy
mulder mulenga mulindwa mullan muller mulligan mulugeta mulwa mumba munasinghe munoz munro munshi
munteanu munthali munyaneza munyao murakami murata muriuki murphy murray murthy murugan musa musil
musoke musyoka mutabazi mutai mutambara mutasa mutemi muthu mutinda mutiso mutlu mutsvangwa mutua
mutuku muwonge muñoz mvelase mwale mwamba mwangi mwanza mwape mwase mwaura mwendwa mwila myers
mzimela méndez mészáros möller møller müller n'guessan nabukenya nabwera naciri nader nagai nagle
naguib nagy nah nahyan naidoo naidu naik nair najafi najjar nakagawa nakajima nakamura nakano
nakato nakayama namachanja nambiar namboodiri nambudiri namdar namgyal namutebi namwala nanayakkara
naqvi narayan narayanan nascimento nasr nasrallah nassar nasser natarajan nath natividad naumov
navarro navratil nawaz nayak nazari nazarov nazir ncube ndaba ndayisenga ndiaye ndikumana ndip
ndlela ndlovu ndolo ndungu nduwayo neagu nedelcu negash negi negri negussie neill nel nelson nemec
nemeth nepomuceno neri nesterov netshitenzhe neumann neupane neves newman ng ngcobo ngema ngetich
ngidi ngo ngoma ngu ngubane nguessan ngugi nguyen nguyễn ngwenya ngwira ngô nhlapo niang niazi
nichols nicolae nicolas nielsen niemi nieminen nieto nikiforov nikitin niknam nikolaev nikolaidis
nikolic nikolić nikolopoulos nilsen nilsson nishida nishimura nissen nistor niyonzima njenga
njoroge njuguna nkabinde nkandu nketia nkhoma nkomo nkosi nkoulou nkrumah nkuna nkurunziza nnamdi
noguchi noh nolan nomura norbu nordstrom noronha norris nortje nour nouri novak novikov novotny
novák nowak nowakowski nowicki nsele nsengiyumva nshimiye nsubuga ntawukuriryayo ntsikana ntuli
nugent nunes nunez nur nwachukwu nwafor nwankwo nwokolo nwosu nwoye nxumalo nyaga nyamweya nyarko
nyathi nyberg nygard nyirenda nystrom nyström nzeyimana nzimande nzioka németh núñez němec o'brien
o'callaghan o'connell o'connor o'donnell o'grady o'hara o'keeffe o'leary o'malley o'neil o'neill
o'reilly o'rourke o'shea o'sullivan o'toole obeng oberoi obiora obrien obure obuya ocallaghan
ocampo ocen ochieng ochoa oconnor ocran odhiambo odili odinga odongo odonnell oduro odwyer ofarrell
ofoegbu ofori ofosu ogawa ogbonna ogilvie ogola ogrady ogu oguejiofor ogunbanjo ogunbiyi ogundipe
ogunleye ogunsanya ogunyemi ogwang ohara ohayon ohno oikonomou ojwang okada okafor okamoto okeeffe
okeke okello oketch okidi okoli okonkwo okoro okot okoth okpara okumu okwir okyere oladipo olah
olaniyan olatunji olawale olayinka oling olisa oliveira oliver olivier oliynyk oloo olowookere
oloya oloyede olsen olson olsson olszewski olumide oluoch olwoch oláh omalley omar omolo omondi
oneill ong ongom oni onifade onishi ono onuoha onwuka onyango onyeama onyekachi ooko oommen
oosthuizen opio opiyo opoku oppong oprea oreilly orekhov orlando orlov orourke orozco ortega ortiz
orwa oryem osei oshea oshima osipov osman osorio ospina ostrowski osullivan oswal ota othman otieno
otim otsuka ouali ouattara ouma ovchinnikov owen owens owino owusu oyarzun oyebanji oyelaran
oyetunde oyewole oyugi oza ozawa ozcan ozdemir ozer ozkan ozturk pacheco padilla pagano pahlavi pai
paiva pal palaniswami palma palumbo pande pandey panditharatne panganiban pangilinan panicker panov
papadakis papadopoulos papanikolaou papp pappas paramanik paredes parekh paris parisi parks parmar
parra parsa pascual patel pathan pathirana patil patterson patwary paul paulsen pavic pavlenko
pavlidis pavlov pavlovic pavlović pawar paweł pawlak pawlowski payet payne pearson pedersen peeters
peiris pellegrini pelletier pena peng pereira perera peretz perez peric perkins perrier perrin
perrot persson peters peterson petre petrenko petridis petrov petrova petrovic petrović pettersen
pettersson peña pfeiffer pham phan philip philippe phillips phiri phogat phua phạm picard pichler
pierre pietrzak pillai pillay pinto piotrowski piras pires pizarro poddar pohl poirier pokhrel
pokorny pokorný polak polat poli policarpio polishchuk polyakov ponomarenko ponomarev popa popescu
popov popovic popović porcu pospisil postma potapov potgieter potocnik poudel poulsen powell powers
prabhu prasad preda premadasa prempeh pretorius prevost prieto prins pritchard probert prochazka
procházka prokhorov prokofiev prosser puri pålsson pérez qassem qazi qian qin qiu quach quaye quek
quezon quiambao quigley quinn quintero quirino quispe qureshi qwabe racz radebe radovic radu radwan
ragab raghavan rahim rahimi rahman rahmani rai rajabi rajagopalan rajakaruna rajan rajapaksa rajput
raju ramabulana ramachandran ramadan ramaite raman ramaphosa ramaswamy ramezani ramirez ramos
ramovha ramsay ramsey ramírez rana ranasinghe randhawa rantanen rao rashad rashid rasmussen
rathnayake rathore ratnayake rauf ravhura rawat rawlings raza rebello reddy rees reeves regan
regassa regmi rehman reid reilly reiter remy ren renard renaud renault restrepo retief rey reyes
reynolds rezaei rezaie rhodes rhys riaz ribeiro ricci ricciardi richards richardson richter rinaldi
rios riquelme rivas rivera riviere rizal rizk rizvi rizzo robbins roberts robertson robinson robles
rocha roche rodgers rodionov rodrigo rodrigues rodriguez rodríguez rogers rojas rolland roman
romano romanov rono rooney roque rosales rosen rosenberg rosenfeld rosenthal rossetti rossi rossouw
rostami roth rotich rousseau roussel roux roy royer rubin rubinstein rubio rudenko rueda rugambwa
ruggiero ruiz rumyantsev rupasinghe russell russo rusu rutkowski ruto rutto ruzicka ryan ryu rácz
růžička saad saade saarinen saavedra sabah sabbagh sachdeva sackey sadeghi sadowski saeed saez
safavi sagna saha sahin sahle sahni sahota saini saito sajjad sakai sakala sakamoto sakho sakurai
sala salah salako salama salazar saldanha saleem saleh salem salgado salinas sallam salman salminen
salo salonen salunke salvi samarasinghe samatar sambo samir samra samuelsson san_jose san_juan
san_martin san_miguel sanchez sandberg sandhu sandoval sandu sanfilippo sangare sangha sangweni
sani sankoh sanna sanneh sano santa_cruz santana santiago santoro santos sanz sapkota saraf sarkar
sarker sarkis sarmiento sarpong sarr sartori sarwar sasaki sassoon sastry sato sauer savchenko
savchuk savelyev savic savin savolainen sawant sawe sawicki saxena sayed sayegh sayyed scanlon
schafer schmid schmidt schmitt schmitz scholten scholtz scholz schouten schreiber schroder schröder
schubert schulte schultz schulz schulze schumacher schuster schwartz schwarz schäfer scott sebata
sedlacek sedláček segal seidel sekgobela sekhon seleka selim selvaraj semenov sen senanayake
seneviratne sengar sengupta seo seok seow sepulveda sequeira serban sergeev serra serrano sesay
sethi seyoum sezer shabalala shafik shah shaheen shahid shaikh shalaby shami shamwana shange
shankar shao shapiro sharaf shariati sharif sharifi sharma sharmarke shastri shcherbakov shehu
sheikh shelton shen shenoy sheridan sherif sherman sherpa shetty shevchenko shevchuk shibata
shiferaw shilubane shimabukuro shimizu shinde shiraishi shirazi shire shivambu shrestha shukla shum
sia siame sibanda sibiya siddiqi siddique siddiqui sidhu sidibe sidorov sikazwe sikder sikora silva
silverman silvestri sim simbeye simek simelane simic simiyu simmons simoes simon simonov simpson
sims simsek simwanza simões sinclair singh singhal sinha sipos siqueira sirisena siriwardena
sirleaf sison sisulu sithole siu sivakumar sjoberg sjöberg skvortsov slattery sleiman slimani
smirnov smirnova smits smuts sng snyder snyman soares sobolev sobukwe soderberg sofronov sohn
sokolov sokolowski solanki solano solberg soler solheim soliman solis soloviev soltani somayajula
sommer song soni sood sooriyaarachchi sorensen soriano soro sorokin sorokina sorrentino sosa sossou
sotho soto sousa souza sowande soyinka srinivasan srivastava ssebunya ssemakula stan stanciu
stanescu stankovic stanković stanley stavrou steele stein steiner stepanek stepanov stephens
stepien stevanovic stevens stevenson stewart steyn stoica stojanovic stojanović strydom stuart su
suarez subedi subramaniam subramanian sugawara sugimoto sugiyama suleiman sullivan sultan sultana
sumulong sundaram suri sutton suzuki svendsen svensson svoboda swaminathan swanson sweeney sy
sydorenko syed sykora sylla szabo szabó szczepanski szeto szewczyk szilagyi szilágyi szymanski
szymański sánchez söderberg søren sørensen tabet tabi tabrizi tadesse taheri taiwo tajima takacs
takada takagi takahashi takeda takeuchi takács talukdar talwar tamang tamba tambo tamura tan tanaka
tanase tandon tanedo taneja tang taniguchi tano tanoh tanui tapia tarafder tarasov tariq tas tashi
tavares tawfik tawil taye taylor tazi tchalla tchamba tchibozo tchouameni tefera tehrani teixeira
tekin tekle tello tembo temu tennakoon tenzin teo terblanche tergat tesfaye teshome tessema testa
tetteh tezuka thai thakkar thakur thambirajah thani thapa theodorou theron thiagarajan thiam
thilakaratne thomas thompson thomsen thornton thuo tian ticona tierney tikhomirov tikhonov tilahun
timmermans timofeev tinubu tiong tiongson tiote titov tiu tiwari tkach tkachenko tkachuk tobin toh
tolentino toma tomas tomaszewski tomic tomita toor torok torres toth toumi touray toure tran traore
tretyakov triantafyllou trieu trinh trinidad tripathi trivedi trofimov truong trần tsang tse
tshabalala tshangana tshivhase tshuma tshwete tsikata tsuchiya tsui tsukamoto tsvetkov tubman tudor
tuncer tuominen turan turay turunen tuwei twagirayezu twum tyler tóth török uche uchida uddin udoh
ueda ueno ugwu umar umeh ungureanu unnithan upadhyay upadhyaya uppal uribe urquhart uslu usman
usmani uwase uwimana uys uysal vaghela valdez valencia valentini valenzuela van_asten van_basten
van_beek van_buuren van_dam van_damme van_de_ven van_den_akker van_den_berg van_den_bosch
van_den_broek van_den_heuvel van_der_berg van_der_heide van_der_heijden van_der_horst
van_der_linden van_der_meer van_der_merwe van_der_plas van_der_pol van_der_sar van_der_stoep
van_der_valk van_der_veen van_der_wal van_der_walt van_dijk van_dongen van_doorn van_eijk van_es
van_gaal van_gils van_gogh van_halen van_haren van_heerden van_hout van_kampen van_leeuwen
van_lieshout van_loon van_niekerk van_nistelrooy van_oosten van_persie van_rensburg van_rooij
van_staden van_veen van_vliet van_wijk van_wyk van_zanten van_zyl vandenberghe vander_meer vandi
vanek varadarajan varga vargas varghese varier varma vasconcelos vasic vasile vasileiou vasiliev
vasquez vasseur vaughan vaughn vavra vaziri vazquez vega velasco velasquez veldhuis velez venda
venkataraman venkatesan venkatesh venter ventura vergara verhoeven verma vermeersch vermeulen
vesely veselý vestergaard vicente vidal vidmar vieira vilakazi vilca viljoen villalba villanueva
villegas vinogradov virk virtanen visagie visser viswanathan vitale vithanage vitiello vlachos vlad
vlasov vlcek vo vogel vogt voicu voigt volkov von_bismarck von_braun von_der_leyen von_hagen
von_neumann von_ribbentrop von_richthofen von_stein von_trapp vora vorobyov voronin voronov vorster
vos vu vukovic vázquez wachira wada wadhwa wafula wagner wainaina walczak walia wallace wallin
walters wamalwa wambugu wamukoya wang wangchuk wangila wanigasekara wanjala wanyama wanyoike
warraich warrier warsame washington watanabe watkins watson watts waweru weah webb weerakoon
weerasinghe weerawardena wei weinberg weinstein weiss wekesa welch wells werner wessels whelan
whitaker wickramasinghe wickremasinghe wieczorek wijayawardena wijeratne wijesinghe wijetunga
wijeweera willems willemsen williams williamson willis wilson wimalasena wimmer winkler wisniewski
witkowski wiśniewski wojciechowski wojcik wolde wolfe wolff wolters wondimu wondwosen wong woods
worku wouters wozniak woźniak wrobel wroblewski wróbel wu wysocki wójcik xaba xasan xavier xhosa
xia xiang xiao xie xiong xu xue xulu yaacoub yacoub yadav yakovlev yakubu yalcin yalçın yamada
yamaguchi yamamoto yamashita yamazaki yanez yang yao yapi yapo yasin yassin yasuda yates yau yavuz
yazdani yeboah yego yengwa yeom yeung yildirim yildiz yilmaz yimer yirga yohannes yokoyama yong
yoon yosef yoshida yoshikawa yousaf yousef youssef yu yucel yudin yuen yulo yupanqui yusuf yücel
yıldırım yıldız yılmaz zachariah zadi zafar zaha zaher zahra zahui zaidan zaidi zaitsev zajac zając
zakharov zaki zalewski zaman zamfir zamora zand zanetti zanini zapata zare zawadzki zayed zeleke
zeman zeng zengin zerihun zerouali zewdu zhang zhao zheng zhong zhou zhu zhukov zhuravlev zia
ziadeh ziegler zielinski zieliński zimmerman zimmermann zogbaye zografos zokora zondi zou zouaoui
zu_guttenberg zubairu zuckerman zulu zuma zungu zuniga zupan zwane zwart álvarez åberg çakır çelik
çetin öberg özdemir özkan öztürk ünal černý đorđević đặng đỗ şahin şimşek
"""

# Surnames that are also ordinary words.
WEAK = """
aka akin amar amin assi ates ba bae bah bailey baker bang barber barker baron beck beg bell berg
berry bhat bile bishop black blanc bond bor boyer brand brink brown burgess burke burton bush
butler butt can carpenter carr cha chapman chew chin chow clark cole collins cook cooper cousin cox
cross curry dang dao day dean dib ding do doe dong els fall fan fang fisher fletcher foo ford
fowler fox frank freeman fu fuller gal garner gentile gilbert goel gong graham grant gray green
griffin gross ha hadj hail hale hall hao hardy hart he hill hogan holm holt hong horn hove human
hung hunt jager jama jara jean kale kan king kiss knight ko kos kral kwan la lai lambert lane
laurel law lei levin lewis lie lien lis little lo lobo long love luna ly lynch ma madden mamo man
mane mani manning mao martin mason may meng miller millet min mire mo moon moore mora more morel
morgan morin morris moss moyo mun muse na nam nash neal neo newton noel obi oh otto pace page
palmer pan pang pardo park parker parry pastor perry piccolo pierce pino poon pop porter potter
power price pugh rani ray reed reis rice riley riva robin roble roger romero rose ross rutherford
sanders sane sang sari schneider seah seck sharp shaw shi shim shin sima sin smit smith soh son sow
spencer stern stone strand sun sung swart ta tae taha tam tao tau tay terry tong tucker turk turner
tutu unal urban vera villa vincent wade walker wall walsh walter wan ward warner warren weaver
weber wee west wheeler white wilk winter wolf won woo wood wright yan yap yapa yaya ye yeo yin yip
young yuan zein
"""
