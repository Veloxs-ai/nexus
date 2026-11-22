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

"""Extra given names for PII detection: South Asian (data only, casefolded, packed).

Indian (every region), Nepali, Sri Lankan, Bangladeshi, Pakistani, Tibetan and Himalayan given
names and common nicknames, on top of the knowledge-graph given names
(``nexus.processing.graph_names``). ``ner_names.given_names()`` builds the set on first use.
"""

from __future__ import annotations

# Given names (not already in the knowledge-graph lexicon).
PACKED = """
aabha aabid aabroo aadesh aadhav aadhira aadil aaditya aadvik aadya aafreen aahana aahil aakar
aakash aakriti aalam aaliya aalok aamir aamna aanchal aanya aaqib aaren aarna aarohi aarush aarvi
aaryahi aaryan aasha aashi aashiq aashka aashna aashritha aashvi aasif aasim aastha aatif aatreyi
aayush aayushi aban abani abbas abdulla abeer abhang abhijeet abhijnan abhilash abhilasha abhimanyu
abhinandan abhiram abhirami abhiramya abhirup abhishri abhyuday abhyudaya abid abida abinash abrar
achint achumbemo achutan adarsh adeeba adeel adhavan adhira adhvik adi adil adinarayana adithyan
advay advika adviti adwait aejaz afaq afia afif afnan afra afreen afrin afroz afsana afshan aftab
afzal agastya agni agrim ahaan ahalya ahana ahanthem ahilya ahlam ahsaan ahsan ahteram ahtesham
aikya aishu aishwarya aiswarya ajayan ajaykumar ajeet ajinkya ajith akaash akalya akanksha akarsh
akbar akeel akeela akhand akhila akhilandeswari akhilesh akhtar akif akmal akriti akshada akshara
akshat akshita alagappan alaka alakananda alam alamelu alamin albina aldous alemla alfaz alhad alia
alim alisha alishba alka allwyn aloysius alphonsa altaf altamash alvina amaan amaira amal amala
amandeep amanjot amanpreet amardeep amaresh amarinder amarjit amarnath amarpreet amatullah amayra
ambika ambily ameena amenla amey amiben amila amisha amitabh amitesh amiya amjad amodh amrik
amrinder amrisha amrit amritbir amritpreet amruta amrutha anagha anahita anaisha anamika
anandakrishnan anandhi anant anantha anarkali anas anasuya anaya anayra anbarasan anchal aneesa
aneesah ang angad angchuk angira angmo angom anguri anhad anika aniket anila anilkumar anindita
anindya anirudha anirvin anisa anish anisha anisur anitha anjaiah anjalika anjana anjaneyulu anjor
anju anjum anjuman ankush anmol annamma annapoorna annapurna anokhi anoop anoushka ansar anselm
ansh anshika anshu anshumaan anson anto antony anubha anubhav anuja anupama anura anuradha anushka
anushree anusree anusuya anvay anvi anvika anwesha aosenla aparajita aparajitha apeksha apexa
apoorva appala appalaraju appu apurva aqeel aqsa arabinda aradhana aradhya arambam arasu arathi
arati arav arbaaz arbaz archa archis archit ardra aref arfa arghya arhaan arham arif arifa arivu
arjunan armaan arman arnaav arnika aroha arohan arohi arooj arpan arpit arsalan arsh arshad
arshdeep arshi arshia arshpreet arti arul arumugam arunakumari aruni arunima arunkumar arunoday
arushi aruvi arvinder arwa arya aryahi aryan arzoo asad asangba asanka asfia asghar ashalata
ashalatha ashan ashar asharani ashfaq ashima ashlesha ashokan ashraf ashutosh ashvik ashwini asim
asit aslam asma asmi asmit asmita asokan aspi aspy asra asrar asutosh aswath aswini atanu atchutha
ateeq ateeqa atharv atharva athira athul atif atiya atreyi atula atulya augustine auranzeb avadh
avadhut avani avantika avijit avikshit avira avleen avneet avni avtar avyaan avyukt ayaan ayan
ayana ayansh ayat ayesh ayla ayra ayub ayushi ayushman ayyappan azaan azad azeem azhar azhor azim
azmat azmi azra babar babita babul babuli babykutty badal badar badondor badri badruddin bahadur
bahdeng baidyanath baiju bakhshish bakhtavar bakhtawar bakordor bakyrshan balachandran balagopal
balakrishna balan balasubramanian balasubramanyam balayya balbir baldev baljeet baljinder baljot
balkar balkaran balkrishna balraj balram balvinder balwant balwinder banamali bandashisha banita
banke bankey bano banri bansan bansari banshanlang bansi bantei banwari bappa bapsy bareera barisha
barkat barnabas barun basant basanti basavaraj bashar basheer bashir bashiran bashisha basit basma
basudev batool bayardolly behram behroze bendang bendangla bennet benny bhabani bhaben bhadresh
bhagat bhagirathi bhagwan bhagwant bhagwati bhagyalakshmi bhagyashree bhagyashri bhairavi bhajan
bhakti bhalchandra bhanu bhanubhakta bhanumathi bhanupriya bharani bharatbhai bharathi
bharathidasan bharati bhargab bhargav bharti bhaskararao bhaskarjyoti bhavesh bhavik bhavin bhavya
bhawani bhawna bhikhu bhim bhima bhimrao bhola bholanath bholu bhoomi bhoomika bhoopendra bhrigu
bhumi bhumika bhupal bhupat bhupen bhupendra bhupesh bhupinder bhupinderjit bhuri bhushan bhutia
bhuvan bhuvana bhuvaneshwari bhuwan biakthansangi bibhas bibhuti bidhan bidisha bidyarani bidyut
bihari biharilal bijan bijay bijaya bijoy bijoya biju bijumon bikash bikram bikramjeet bikramjit
bilqis bimal bimala biman bimla bimlesh bimola binal binayak bindhu bindu bini binita binod binoy
binu bipasha bipin biplab bipul biren birendra bishal bishnu biswajit biswanath bittu boman bomi
bonti braganza brahma brahmaiah braj braja brightstar brijbhan brijesh brijkishore brijlal
brijmohan brijpal brijraj buddhika bunty burhan burjor bushra caetano carmelina cawas chacko chahat
chaitali chaitanya chaitra chaitrali chaitrika chakradhar chakravarthy chakri chalapathi chaman
chamara chamari chameli chamila chaminda champabai chanchal chand chanda chandam chandana chandani
chandima chandini chandrakala chandrakant chandramohan chandramouli chandran chandrasekhar
chandrasekhara chandrasekharan chandrashekhar chandresh chandreyi chandrika chandu chaoba charan
charanjit charanpreet charu charulata chathura chathuri chawngthu chellamma chellappan cherian
cheriyan cheshta chetak chetana chetanpreet chetna chhana chhaya chhering chhetan chhewang chhime
chhingpuii chhoki chhonzom chhotelal chhuanvawra chimi chimmi chinchu chingkheinganba chinmay
chinmayi chinmoy chinna chinnaiah chinnasamy chintan chintu chiraag chirag chiranjeevi chiranjib
chirayu chitrang chitrangada chitranjan chittaranjan choden choedon choki chokyi chosphel chotelal
chotu chunni chunnilal chunzom cini cletus cornelio cyrus dabeer dagdu dairya daksh dakshata
dalarilin daler dalip daljeet daljit dambar dambaru damodar dania danish dany danyal daraius darika
darnghaka darpan darsh darshan darshana dasaratha dasel dasun dattaram dattatray daulat davinder
davis dawa dawood daya dayal dayalan dayan dayana dayanand dayashankar debabrata debarati debashis
debasish debdas debendra debjani debnath debolina debopriya dechen deeba deepali deepesh deepinder
deepinderjit deepmala deepthi deepti deki delek dema denny deskit devadas devadathan devaiah devaki
devan devansh devaraj devarajan devarsh devi devika devraj devrath devyani dhairya dhanabir
dhanalakshmi dhanamanjuri dhananjay dhanapal dhanashree dhandapani dhaneswar dhani dhanpat dhanraj
dhanvi dhanya dhanyasree dhapu dhara dharam dharampal dharani dharini dharmendra dharmesh dharmik
dharmpal dharmraj dharmveer dharshini dhatri dhaval dhavan dhiraj dhiren dhivakar dhivya dhiyanesh
dhondiba dhondup dhriti dhrubajyoti dhrubo dhrumil dhruva dhruvi dhurba dhwani dhyan dhyani dibon
dibyendu dickyi digambar diganta diksha dil dilani dilawar dilbag dileep dilesh dilhara diljit
diljot dilli dillip dilnawaz dilpreet dilraj dilruba dilshad dilshan dilshani dilum dimpal dimpi
dina dinanath dindayal dinesha dinshaw dinuka dipak dipali dipankar dipanwita dipendra dipika dipti
dipu disha diskit divakaran divija divit divyani divyansh divyanshu divyesh dnyaneshwar dolat
dolkar dolma domnic donbok dorjay dorje dorjee dorphang dossa drashti draupadi drisya drolma
dropadi dukhi dukpa dulal dulani dulanjali dulari dunstan dupgyal durba durgaprasad durgarao
durgesh duryodhan dushan dushantha dwarkanath dwij dymphna dyuti eapen easwaran ebin ebor eesha
eeshan ehaan ehsan ehtesham ejaz ekaansh ekaja ekam ekansh ekta elahi elango elavarasan eldho
eldorado eldose elina elsy eman ephraim erach eralu ermelinda esha eshaal eshaan eshal eshan
eshanvi eshwari eswar eswari eusebio ezhilarasi fahad faheem fahim fahima fahmida faiz faiza faizan
fakhar fakhra falak falgun falguni fanwell faqir faraz fareed fareeda farhad farhana farheen faria
farida fariha farokh farooq farukh farwa farzana fateh fatehchand fatehjang fatema fauzia fayaz
fazal fazila fehmida femina fenil fernandes feroz feroza fidelis filomena firdaus firdosh firoz
firoza fiza floriano foram fousiya fouzia freny fulki gagan gagandeep gaganjot gaggi gajalakshmi
gajanan gajendra ganapathy ganesh ganeswar gangadhar gangadhara gangaraju gangaram gangasagar
ganpat ganpatrao gargee gargi garv gatik gaurang gauravi gauri gaurika gautam gayan gayani gayathri
gayatri gazala geetanjali geethu geetika gev ghanshyam ghanshyambhai ghazala ghufran ghulam gigi
gihan gimhani girdhari gireesh giri girija girirajan girraj gitali gitanjali gleeson gnanasekaran
gnaneshwar gobind godfrey gogi gokulakrishnan gokulesh gomathi gomathy gomti gonbo gopa gopakumar
gopalakrishna gopalakrishnan gopi gopika gopinath gopinathan gorakh gouri govardhan govinda
govindan govindarajulu gracy greeshma guddi guddu gudiya gulab gulabi gulabo gulbadan gulfam
gulistan guljar gulnar gulnaz gulrukh gulshan gulzar gunajit gunasekaran gundeep guneet gunika
gunjan gunjot gunmeet gunvant gunveen gunwant gurbachan gurbaksh gurbinder gurcharan gurdas gurdeep
gurdev gurdial gurinder gurjant gurjeet gurkamal gurkirat gurlal gurleen gurmail gurmeet gurmit
gurmohan gurmukh gurnam gurnoor gurpal gurpartap gurpyare gursahib gursewak gurshaan gursharan
gursimar gursimran gurtej gurudas gurveer gurvinder gurwinder gyalmo gyaltsen gyan gyanchand
gyanendra gyaneshwar gyanu gyanvi gyatso habiba hadiya hafeez hafsa haider hajra hajrah hamdan
hameed hamid hamida hammad hanan hanif haniya hansika hansraj hanuman hanumant hanumantha
hanumantrao harbhajan hardeep hardev hardik hardika hargun haridas haridasan harihar hariharan
harikrishna harikumar harilal harinder hariom haripad hariprasad haripriya hariram haris
harishankar harita harjeet harjinder harjot harkesh harkirat harleen harman harmandeep harmanpreet
harmeet harmohan harnam harnarayan harnek harpal harshad harshada harshal harshil harshini harshita
harshvardhan harshvi harsimran harsimrat harvansh harvinder haseeb haseena hashan hashim hashir
hasina hasini hasitha hasnain hayat heba heena heeya heisnam heli hemal hemalatha hemang hemangi
hemangini hemanta hemavati hemchand hemlata hemraj hemwati hena hermenegildo hetal hetansh hetvi
hibba hilal himani himanshu hira hiral hiralal hiranya hiren hiruni hishaam hiten hitendra hitesh
hitul hiya hlimpuii hmangaihzuali hmingthanzuali homi hoor hoshang hridaan hriday hrishi hrishikesh
hrithik huma husain husna husnain hussaina hussaini hymavathi iaishisha iawan ibanri ibemhal
ibeyaima ibhan ibohal ibomcha ibotombi ibungo idhant idika idris iftikhar ignatius ihaan ihit ijaz
ikram ikshita ila ilamathi ilesh ilyas iman imarti imlong immanuel imnainla imoba imon imti imtiaz
imtiyaz inaaya inacio inam inaya inayat inbavalli inder inderjeet inderpal inderpreet indhumathi
indra indrajeet indrajit indrani indrapal indrasen indrasena indravadan indulekha indumati inika
iniya intizar iohborlang iolang iqbalpreet ira irah iresha irshad irtiza irum isha ishan ishani
ishaq ishika ishrat ishtiaq ishvi ishwar ishwarbhai ishwari ismail issac isuru ivaan ivanya
iyyappan jaan jabbar jaber jacinta jaffar jagabandhu jagadeesan jagadeesh jagadeeswar jagadish
jagan jaganmohan jagannath jagat jagdamba jagdeep jaggi jagjit jagmeet jagmohan jagram jagroop
jagruti jagtar jahaan jahanara jahangir jahanvi jahid jahnabi jahnavi jai jaideep jaidev jaimin
jainam jaiprakash jairam jaisal jaishree jaison jalal jalpa jamaal jameel jameela jamir jamna jampa
jamshed jamshid jamtsho jamuna jamyang janak janaka janani janardhan janardhana janhavi janith
janitha janki jankiben jannat jansi jarnail jasbir jasdeep jasika jasim jaskaran jaskirat jasleen
jasmeen jasmeet jasmin jasoda jaspal jaspinder jassi jasvinder jaswant jaswinder jatan jatin
jatinder jawad jawahar jaweed jayabalan jayachandran jayakanthan jayakrishnan jayakumar jayalakshmi
jayani jayanta jayanti jayaprakash jayaram jayaraman jayashree jayasimha jayasree jaydeep jaydip
jayendra jayesh jayeshbhai jayna jaywant jeet jeetendra jeevan jeevika jeewantha jehangir jelina
jenil jeremias jessy jetha jeyalakshmi jhalak jhanvi jharana jhuma jhumpa jiban jibin jibran jigar
jigisha jigme jigmet jigna jignesh jilu jinal jinesh jintu jinu jisha jishnu jital jitesh jithin
jithu jitin jitu jivan jivika jiya jiyansh joban jobanpreet joby jofin jogindar joginder johnson
johny jomon jomy jonali joon josekutty josemon josey joshy jothi jothika jovita joyita joykumar
jubin jude jugal juhi jujhar juma junaid jyothi jyotiba jyotirmayee jyotirmoy jyotsna kaavya kabeer
kabir kabita kaikhushru kaikobad kailash kailashi kailashnath kainat kainaz kaira kairav kairavi
kaizad kajal kakoli kaladharan kalaiselvi kalarani kalavathi kaleem kalim kallu kalpana kalpani
kalpataru kalpesh kalrav kalsang kalu kalyanikutty kamaal kamakhya kamakshi kamalakanta kamalakar
kamalesh kamaljeet kamalpreet kamaraj kamatchi kameshwar kameswari kamila kamini kamlesh kamli
kamran kamta kanagaraj kanak kanaka kanakadurga kanakaraju kanav kanchan kanchhi kandasamy kaneez
kanhaiya kanhaiyalal kanhu kanika kanimozhi kanishka kankana kanti kantilal kanubhai kanwaljit
kanwar kapil kapthianga karamjit karamveer karanveer karna karnail karsang kartar karthiga
karthikeya karthikeyan kartikeswar kartikey karuna karunakaran kashan kashif kashinath kashish
kashvi kasi kasthuri kasturi kasun katy katyayani kausar kaushal kaushalya kaushik kaustav kaustubh
kavan kaveri kavin kavinda kavindu kavish kavisha kavitha kaviya kavyansh kawaljit kayalvizhi
kaynat kayra kedar keerthana keerthi kehar kekhrie kelsang kesang kesar kesari kesavan kesavulu
ketaki ketan ketki kevi kevisetuo kewal keya keyur khagen khairunnisa khaled khalida khando khatija
khem khemchand khiangte khrawbok khrielie khurram khurshed khurshid khushboo khushi khushnood
khushnuma khushru khyati kiaan kimaya kinjal kinley kinnari kirandeep kiranjeet kirit kiritkumar
kirpal kirpreet kirti kishan kishanlal kishanrao kishor kishorchandra kishorekumar kishori
kishorkumar kitbok kobita kochu kochumon kokila komal kordor koteswara koteswari kousalya koushik
kowsalya kripa kripal krish krisha krishnadas krishnaiah krishnakumar krishnamurthy krishnan
krishnankutty krishnaveni krithika kriti kritika kritvi kriya krunal krupa kruti kshama
kshetrimayum kshitij kshitiz kubra kul kulbhushan kuldip kuljeet kuljinder kulvinder kulwant
kulwinder kumaraswamy kumaresan kumari kumud kumudha kuna kunchok kunda kundalik kundan kunga kunj
kunjal kunjan kunjarani kunjumol kunjumon kuntal kunzang kuriakose kurian kushagra kushal kusum
kyra kyrmen laali labdhi lachhman laddi lahiru laiba lajja lajwanti lakhan lakhbir lakhi lakhimi
lakhpat lakhvir lakhwinder lakmal lakmini lakpa laksh lakshan lakshana lakshay lakshita lakshmaiah
lakshman lakshmana lakshmanan lakshmikutty lakshminarayana lakshmipathi lakshya lakyntiew lal lalan
lalawmpuia lalbiakdika lalbiakmawia lalduhoma lalengmawii lalfakzuala lalhlimpuii lalhmangaihi
lalhmingliana lalhmunmawia lalhriatpuia lalhruaitluanga lalita lalitha lalithamma lalji lallan
lalliantluanga lallu lalmalsawma lalmani lalmawia lalmuanpuia lalmuanpuii lalnghinglova lalnunmawia
lalnunpuii lalnunsanga lalnunzira lalpekhlua lalramliana lalramsanga lalramthara lalremsiama
lalrinawma lalrindika lalrinpuia lalropui lalrosanga lalruatfela lalsangzuali lalsawmliana
lalsawmvela lalsiamthara laltanpuia lalthanmawia lalthansanga lalthanzara lalthazuali lalthlamuana
lalthlengliana lalthuamluaia lalthuthleng lalu lalvarmawii lalzarmawia lalzuithanga lambok lamlang
lamphrang lamya lanunungsang larsing lasantha lasith lateef latha latif lavina lavish lavkush lawan
laxman laxmi laxmibai lazarus leela leelamma leena leimapokpam leishemba lekha lekhansh lekhraj
lekshmi lepcha lhaki lhakpa lhamo lhundup lianchhawna liandailova lianhlupui lianmawia lianthangi
lijo liju lijumon lincy linto lipika lipokmar lipsa lissamma lissy liton liyaqat lizy lobsang
lochan logeshwari lohit loken lokenath lokendra lokesh lona lonchen longkumer lopa lopamudra losang
lourembam lourenco lovepreet lubna lutfi lyngdoh mable madan madanlal madhab madhan madhankumar
madhavarao madhavi madhawa madhukar madhumita madhura madhurima madhusudan madhvi madiha madushani
magesh mahad mahadeo mahadev mahadevan mahadevi mahalakshmi mahalingam mahasweta mahaveer mahavir
mahboob mahbub mahek mahela mahendra mahesan maheshwari maheswari mahi mahika mahima mahin mahinder
mahir mahira mahjabeen mahjabin mahmood mahnoor mahua mahum maimoona maira mairah mairang maitreyi
makarand makhan malaika malati malavika malay malika malith mallesh mallika mallikarjun
mallikarjuna malsawmi malsha mamata mamina mampi mamun manab manan manas manasa manasi manaswini
manav manavi manbhari mandar mandeep mandira mangal mangamma mangat mangeram mangesh mangi manickam
manidipa manik manikuttan manikyala manimegalai maninder manita manivannan manjeet manjinder
manjiri manjit manjot manju manjula mankirat manmeet manmohan mannat mannu manohar manoharan
manohari manorama manoranjan manorma manphool manraj mansi mansoor mansur manthan mantosh mantu
manu manveer manvi manvik maqbool mariamma marimuthu marisa mariyam marwa maryam mashal mashhood
masood masud mateen mathews mathi mathivanan maulana mausumi mawia mawii mayank mayra mayukh mayur
mayuresh mayuri mayurika mazhar mebanshisha mebarisha medha medolenuo meenal meenatchi meenu megh
meghal meghna mehak mehboob meher mehernosh mehfooz mehli mehnaz mehr mehreen mehta mehtab mehul
mehvish memcha memchoubi merlin mervyn metok mevan meyyappan midhun midhuna migmar mihika mihir
mihit milind minahil minakshi minal mingma minhaj mini minimol minoli minoo minu mira misbah misha
mishka mishti mital mitali mitesh mithlesh mithoo mithun mitra mitu mitul mivaan mizanur moazzam
moeen mohana mohanasundaram mohandas mohanlal mohanraj mohanrao mohd mohendro mohib mohinder mohit
mohsin mohsina mohua moin momin mondeep monir monisha monu moolchand morup motilal mridu mridul
mridula mrigank mrinal mrinali mrinalini mrinmayee mrinmoy mrugesh mrunal mubarak mubashir mudassar
mueen mugdha muhammad mujeeb mukarram mukhtar mukta mukul mukund mukunda mukundan mukut mumtaz
munawar munazza mundri muneeb muneera munesh munia munir muniraj munish munmun munna munni
muralidhar muralidhara muralikrishna murlidhar murtaza musarrat muskan muthukumar muthulakshmi
muthuraman muthusamy muzaffar muzammil myraa myrah naamya nabajyoti nabanita nabaraj nabarun nabeel
nabila nabin nachhattar nachiket nachiketa nadeesha nadir nadira nadiya nafees nafeesa nafisa
nagabhushanam nagalakshmi nagamani nagappan nagarajan nagaraju nagarjun nagarjuna nagavalli
nagendra nagesh nageswara nageswari nagnath nahar nahid nahida naincy nainesh nainika nair naitik
najeeb najma naksh nakshatra nakul nalin nalini nallamuthu namal namdeo namgay namgyal namita namra
namrata nanao nanda nandakishore nandakumar nandan nandana nandish nandita nandkishore nandkumar
nandlal nandu nanhi nanthini naocha naorem narasaiah narasimha narasimhulu narayan narayana
narayanamma narayanan narendra nargis narhari nariman narmada narsingh naseem naseer nashit nasima
nasreen nasrin nasrullah natarajan nathu nathuram natwar naureen naushir navaz navdeep naveed
naveenkumar navika navin navkiran navneet navpreet navroop navya nawal nawang nawaz nayab nayan
nayana nayanmoni nayantara nayeem nayra nazeer nazia nazim nazir nazma nazmin nazneen
nedunchezhiyan neel neela neelakandan neelakanta neelesh neelima neelkanth neerav neeru neetu nehal
neiphiu neisalie nelly nergish nethmi netra neysa ngawang nibedita nida nidhi nigam nigar nihal
niharika nikhat nikhila nikku nikunj nilakanta nilam nilamadhab nilanjan nilanjana nilay nilima
nilkanta nilkanth nilofar nilufar nilufer nilutpal nima nimal nimali nimesh nimi nimisha nimmi
nimmy ningthoujam nipon nipuni niraj nirajan nirali nirav nirbhay nirja nirmalamma nirmali
nirmaljit nirmalkumar nirmalya nirmani nirmitee nirupama nirvaan nisal nishan nishant nishanth
nishat nishidh nishit nishita nishka nishtha nital nitara nitesh nithin nithya nithyananda niti
nitish nitu nitumoni nitya nityam nived nivedita niyati niyaz nizam nokdenlo noman nonglang
nongsiej nooran noorjahan noorulain norbu nordun noreen norzin noshin noshir nouman noyonika nudrat
nungsangla nunsangi nupur nurul nusrat nutan nuwan nuzhat nyima nyra nysa obaid oinam ojas okendro
omana omi omisha omkar omprakash omveer oorja orooj oshadi oshin oswald oviya owais paarth pabitra
padam padmaja padmalochan padmanabhan padmavathi padmini pahal pahalwan palak palash palden pallab
pallabi palzom pamma pandharinath pandian pandiyan pandu pandurang pangernungsang pankajakshan
pankhuri pannalal pappi pappu parag param paramasivam parameshwar parameswaran parameswari paramita
paramjit parasram parbati paridhi parimal parineeta parinita parisha paritosh pariza parizad
parmeet parmjit parmod parshuram parshva parthiban parthiv parul parvathy parvati parveen parvez
parvinder pasan pasang passang paulose pavan pavani pavitha pavithra pavithran pavitra pavni pawan
pawandeep payal pelden pema pemba penpa perin perumal pervaiz pervin perviz phaneendra phanindra
phibansharai philomena phiroza phoolwati phuntsho phuntsok phurba phurbu pihu pilloo pinaki pinakin
pinal pinki pinku pishak pistha pitambar pius piyali piyush ponnusamy poojan poongodi pooran poorna
poornima poorvi popy poulami pournami prabakaran prabath prabha prabhakaran prabhat prabhavathi
prabhavati prabhdeep prabhjot prabhleen prabhnoor prabin prabir prachi pradeepan pradeepkumar
pradip pradnya pradnyesh pradyumna praful prafull prafulla pragati pragya prahlad prajakta prajwal
prakashchand pralhad prameela pramila pramod pramodini pranab pranati pranavi pranay pranita
pranjal pranjali pranjit pranshu pranvi prarthana prasanjit prasanna prasannakumar prasanta
prasanth prasanthi prasenjit prasun pratap prateek pratham prathamesh pratibha pratiksha pratima
pratyush praveenkumar pravin pravina preet preetam preethi preetinder preeto prema premchand premi
premkumar premlata prerana prerit prerna prisha pritam prithvi prithviraj priyabrata priyadharshini
priyal priyam priyanshi priyanshu pronami prudencio pugazhendi pulkit punam puneet punit punitha
punnaiah purab puran purna purnendu purnima purshottam purushotham purushottam purvi purvik
pushkaraj pushpa pushpalatha pushpendra puspa puspanjali putul pyari pynbiang pyndap pynskhemlang
qadir qamar qasim qayyum quadir quasar qudsia raahi raayan rabbani rabia rabin rabindra rabiya
rabten rachana rachit rachita radhabai radhakrishna radhakrishnamurthy radhakumar radheshyam radhey
radheyshyam raees rafay rafi rafiq rafiqul raghavan raghavendra raghavendran raghavulu raghbir
raghu raghubir raghunath raghuraj raghuram raghuveer raghuvir raghvendra rahat raheel raheema rahel
rahim rahman rahmat raihan raisa raisha rajagopal rajagopalan rajaji rajalakshmi rajalaxmi rajamani
rajanand rajani rajappan rajaram rajaraman rajarshi rajasekaran rajasekhar rajasekhara rajashree
rajbahadur rajbir rajdeep rajeevan rajendar rajender rajeshwari rajeswari rajib rajinderpal rajit
rajitha rajiv rajkishore rajkumari rajlakshmi rajmani rajmohan rajnath rajni rajnikanth rajnish
rajpal rajrani rajshekhar rajshree rajshri rajul rajveer rajvir rajwant rajwinder rajyalakshmi
rakhi rakib raksha rama ramachandra ramachandraiah ramachandran ramadevi ramakant ramakanta
ramakoti ramakrishna ramakrishnan ramalakshmi ramalingam ramamoorthy ramamurthy ramana ramanaiah
ramanamma ramanathan ramandeep ramani ramanjit ramanuj ramarao ramasamy ramashray ramaswamy
ramautar ramavtar rambabu rambharose ramchandar ramchandra ramdas ramdayal ramdev ramdhari
ramdulari rameez ramesan rameshbabu rameshwar rameshwor ramgopal ramiz ramjanam ramjatan ramkali
ramkishan ramkumar ramkumari ramlakhan ramlal ramnaresh ramnath ramniwas rampal ramphal ramprasad
rampyari ramratan ramsevak ramsingh ramswaroop ramtirth ramu ramvilas ramwati ramzan ranajit ranbir
ranchhod randeep randhir ranganath ranganayakulu rangarao rangbah rangbok ranil ranjabati ranjan
ranjana ranjeet ranjini ranjita ranjith ranjodh rano rapbok rasal rashad rashed rashel rashesh
rashida rashmika rashmita rashna rasik rasika rathi rathin rathna rati ratilal ratna ratnakar
ratnamma ratnesh rattan raunak ravichandran ravikant ravikumar ravindar ravinder ravindra
ravindrababu ravindu ravish ravishankar ravjot ravneet rawat rayaan rayansh raza razi razia rebati
reema reena rehaan rehan rehana rehmat rejani reji remya reni renjini renjith renuka reshmi resmi
revathy revati reyansh riaan rian riaz rida riddhesh riddhi riddhima ridhi rifat rigzin rimai
rimjhim rimpi rimpy rimsha rinal rinawma rinchen rinki rinkle rinky rinto rinu ripal ripon rishabh
rishi rishika rishikesan rishit rishita ritesh ritika rittika rituraj ritvi ritvik ritwik rivaan
rivansh riya riyasat riyaz rizwan roby rochak rochhingpuii rohidas rohin rohitash rojalin rojan
rokeya rokolhu roma romen ronak rongsen rony roohi roop roopa roopchand roque roshani roshni rosily
rosita rothangpuia ruatfela rubab rubeena rubel rubi rubina ruchika ruchira rudhra rudra rudrani
rudransh rufina ruhaan ruhanika ruhi ruhika rujul rukhsana rukmani rukmini ruksana rukshan rumesh
rupali rupam rupesh rupinder rupjyoti ruqaiya ruqayya rushabh rushil rustam rustom ruta rutuja
rutvi ruzbeh saanvi saarth saavi sabbir sabby sabeeha sabeena sabiha sabin sabina sabir sabita
sabitri sabra sabu sabuj sachi sachidananda sachini sachit sachith sadaf sadanand sadashiv sadhana
sadhna sadia sadiq sadiqa sadruddin sadun saee safdar safia safiya safwan sagarika sagor sahan
sahana sahar saharsh sahasra sahdeo sahdev saheli sahibjot saibaba saie saif saifuddin saikiran
saikrishna sailaja sailendra saipriya saira saisha saithanga sajan sajda sajeev sajid sajida sajini
sajith sajjad sajjan sakharam sakhrie sakib sakina saksham sakthi sakthivel salahuddin salamat
salar saleem salman saloni samaira samanthi samar samarjeet samarjit samarth samay samaya samayra
sambasiva sambasivarao sambit sameena sameera samidha samik samiksha samishka samiya samjhana sampa
sampat sampath sampatlal samrat samreen samridhi samruddhi samten samvit samyukta sanahal sanajaoba
sanamacha sanath sanatomba sanatombi sanaullah sanaya sanbor sanchit sanchita sandeepinder sandesh
sandhya sandhyarani sandip sandun sanduni sandya sangay sangeetha sanghamitra sangmo sangram
sangthanga sangzuali sanika sanil sanjeevani sanjenbam sanjib sanjiv sanjivani sanju sanjukta sanka
sankar sanket sanny sanober sanoj sanskriti santan santanu santlal santoshi santra santram sanvi
sanvika sapana saqib sarabjit sarang saraswathi saraswati sarath sarathkumar saravanakumar sarbani
sarbjit sarbjot sarfaraz sarfraz sargun sarika saritha sarju sarmad saroj sarojini sarswati sarthak
sarthi sarvani sarvesh sarvika sarvjeet sarwar sarwat sasanka sashimenla sasidharan sasikala
sasikiran saswati satarupa satbir satheesh sathi sathish sathya sathyamoorthy sathyan satinder
satnam satpal sattar satvir satwinder satya satyabrata satyajit satyam satyanarayana satyavathi
satyendra saugata saumil saumya saurav savio savita savitri savitribai sawan sawindi sayali sayan
sayantan seena seetha sehaj seher sekhose selim selvakumar selvaraj sembian sengbah senthamarai
senthilkumar sentila sentilnathan seshagiri seshu sethu sevak sewali shaanvi shabana shabbir
shabnam shachi shadab shafi shafiq shagufta shahana shaheen shahin shahnaz shahrukh shahzad
shahzeen shaikh shaila shailaja shailee shailendra shailesh shaista shaival shajahan shaji shakeel
shakib shakila shakir shakuntala shakuntla shalu shambhavi shambhu shambhunath shamim shamima
shamita shamji shamna shampa shamrao shamshad shamsher shamshuddin shamsul shanavas shanaya shanaz
shanborlang shanika shankaraiah shankari shankarlal shankarrao shanmugam shanmugapriya shanta
shantanu shanti shanto shanu shanuka shanvi shaon shaphrang shapla sharada sharan sharanya sharayu
sharjeel sharmeen sharmila sharmishtha sharvari shashank shashikala shashikant shaukat shaunak
shaurya shayan shayra shazia sheeba sheeja sheela sheelwati sheena sheetla shefa shefali shehan
shehnaaz shehzad sheikh shekhar shenal shenpen sherab sherin shernaz sherpa sheru shibaji shibani
shibu shijo shiju shikha shilbok shilp shilpi shinda shireen shirish shital shiva shivaay shivaji
shivakumar shivam shivanand shivangi shivanna shivansh shivaraj shivay shivbaran shivcharan
shivdayal shivdutt shivendra shivkumar shivlal shivlingam shivmohan shivnath shivpal shivprasad
shivraj shivram shivshankar shlok shoaib shobana shobharam shobhit shoby shova shozab shraddha
shravan shravya shrawan shreedhar shreekant shreeram shrenik shrey shreyan shreyas shridhar
shrihari shrikant shrinika shripad shriram shrirang shrisha shrivan shriya shrujal shubh shubhada
shubhangi shumaila shuvo shvet shyam shyama shyamal shyamali shyamkali shyamlal shyamsundar sia
sibghat sibi siddhant siddhanth siddhesh siddhi siddhika siddique sidharth sidhu sidra sijo
sikandar silloo simanta simarjeet simarpreet simran simranjeet simrat sindhu singaram singye sini
sirajul sireesha sirisha sita sitabai sitaram sitaramaiah sithara sithum sivabalan sivadasan
sivagami sivaji sivakami sivanandam sivaprasad sivarama sivaraman sivasankar sivasubramanian siya
skalzang skarma smitarani smriti sneh snehal snehalata snigdha sobha sobhana sohag sohaib sohail
soham sohanlal sohel sohini sohkhlet sohrab sombir somenath somwati sonam sonika sonu sopan sorab
sorokhaibam sougata soujanya soumen soumitra soumya sourabh sourav sowmiya spalzes spandana sparsh
srabani sravani sravya sreedevi sreejesh sreejith sreekala sreekumar sreelakshmi sreemoyee sreenath
sreenivasan sreeparna sridevi sridhar sridharan srihari srijan srijana srijit srikala srikanth
srikar srilakshmi srimathi srinidhi srinivasa srinivasan srinivasarao srinivasulu sriram srishti
sruthi stanzin stobdan stuti subash subbaiah subbalakshmi subbamma subbarao subbulakshmi subhadra
subhan subhankar subhashini subhashree subhra subir subodh subramani subramanyam subrata sudam
sudarsanam sudarshan sudeshna sudevan sudhakar sudhakara sudhanshu sudharani sudheer sudheesh sudip
sufiyan sugandha sugriv sugumar suhaan suhail suhana suhani sujan sujatha sujit sujith sujoy
sukanta sukanya sukhbir sukhchain sukhdarshan sukhdeep sukhdeo sukhdev sukhjeet sukhjinder sukhmani
sukhmeet sukhpal sukhpreet sukhraj sukhram sukhwant sukumar sukumaran sulabha sulochana sumaira
sumalatha sumana sumanta sumanth sumathi sumedh sumedha sumeet sumer sumesh sumita sumitra sumon
sunaina sunanda sunayana sundaram sundaravadivelu sundari sundarlal sundarrajan sundeep sunder
sundri suneetha sunitha sunlang suparna supongmeren supratik supriyo supun surajit surekha
surendran surinder surinderpal suriya surjeet surjit suryabhan suryakant suryanarayana suryansh
suryaprakash suseela sushama sushila sushma sushmita susmita suvankar suvarna suyash swagata
swaminathan swapnali swapnil swara swarada swaraj swarit swarn swarna swarnali swarup swathi swayam
swer sweta syam syamala syed tabassum tabish tabrez tahir tahira tahmina taimur tajamul taksh talat
talha talib talwinder tamal tamali tamanna tambor tamilarasi tamizh tamphasana tanaji tanay tandin
tanima tanirika tanisha tanishka tanishq taniya tanmayi tanu tanushree tanveer tanvika tanvir
tanzeem tanzila tapan tapas tapasi tapasvi tapaswini tapasya tapati taposh tarachand tarak tarang
tarannum tarawati tareq tarini tarlochan tarsem tashi taslim tasneem tasnim tauheed tauqeer tauseef
tavisha tawhid tayyab teejan teena tehmi tehmina tehmtan tehseen tehzeeb teibor teja tejal tejas
tejash tejaswi tejaswini tejpal tejram tejveer tejwant temjen temsula tenpa tenzin tenzing tessy
thambi thampi thangaraj thangavel thanghleia thangsanga thankachan thankamma thanmawia tharindu
tharushi thenmozhi thilina thilini thinley thirumalai thiruvengadam thoiba thoibi thouba thubten
thulasi thulasidharan thupten tiameren tijo tika tikaram tilak tinka tiplang tirth tirthankar tisha
titas titu tlangthanmawia tokheli tomba tombi tomy tonmoy tonthoi toshi touseef trayee treilang
tribhuvan tridha tridib tridip trilochan trilok trilokinath trimbak trina trinadh tripat tripti
trisha trishala trishika trishna triveni trivikram trupti trusha tsepak tsephel tserin tsering
tsetan tsewang tshering tsukti tsultrim tuhin tukaram tulasi tulasiram tuli tulika tulsi tulsiram
tulumoni tundup tushita tvisha twinkal ubaid udara udayan udayveer uddhav udeni udhayakumar udit
ugen ugyen ujas ujjal ujjwal ujjwala ujwal ujwala ulka umaima umair umakant umakanta umamaheswara
umamaheswari umang umar umashankar unnati unni unnikrishnan unnimaya upasana upeksha upendar
upendra upkar urgain urja urmila urooj uroosa urvashi urvi utpal utpala utsav uttam uttamjit uttara
uzma vaanya vachan vadivel vaibhavi vaidehi vaidik vaidyanathan vaijayanti vairamuthu vaisakh
vallabh vallabhbhai vallari vamika vamshi vamsi vamsikrishna vanaja vandit vanita vanitha
vanlalhruaia vanlalngheta vanlalruata vanraj vansh vanshika vanya vaqar varalakshmi varaprasad
varenya varghese varsha vasantha vasanthi vasanti vasantrao vasavi vasudev vasudevan vasudha vasuki
vasvi vatsal veda vedaant vedansh vedant vedha vedika vediyappan vedpal vedprakash veena
veerabhadra veeraiah veeramani veeramma veeransh veerpal velan velayutham velmurugan venkata
venkatalakshmi venkatasubbaiah venkateswara venkateswarlu venkatramana vennila venu venugopal vetri
vetrivel viaan vibha vibhor vibhuti vidhan vidhi vidhit vidhya vidula vidur vidyadharan vidyawati
vidyut vigneshwaran viha vihaan vihan vihana vihanga vijaya vijayakumar vijayakumari vijayalakshmi
vijayan vijayasree vijaybhaskar vijaykumar vijender vijendra vikash vikesh vikramjit vikrant vikuo
vilas vilasrao vilie vimala vimlesh vinaya vinayak vinayakrao vineeta vineeth vinita vinitha vinoth
vinothini vinu vipra vipul virag viraj virat virender virendra virpal visalakshi vishakha vishmi
vishnu vishnuprasad vishram vishu vishva vishwa vishwajeet vishwanath vishwas vishwesh vishweshwar
vismay viswam viswanathan vittal vitthal vivaan viviana vizol vrinda vritika vritti vrunda vrushali
vyan vydehi vyom vyomesh wafa waheed wahid wajahat wajid wanbok wandashisha wangchuk wangdu wangmo
wankit wanshisha waqar waqas waseem wasim wati willy winnie xerxes yaashvi yadagiri yadaiah yadav
yadhu yadvinder yadwinder yagna yagya yaima yaiphaba yaisana yaksh yameen yamika yamini yamuna yana
yangchen yangdol yangdon yanger yangki yangzom yaqoob yasar yasas yaseen yashas yashasvi yashika
yashoda yashodha yashodhara yashpal yashvi yashwant yashwantrao yasin yasir yasiru yasmeen yatharth
yatin yawar yazdi yazhini yedhu yella yellamma yengkhom yeshe yeshi yezdi yogendra yogeshwar
yogeswara yogini yogiraj yogita yohan yonten younus yubaraj yudhishthir yug yugandhar yunus yuvaan
yuvan yuvaraj yuvarani yuvasri yuvika yuvraj zaara zabeen zacharia zachariah zafar zafira zaheer
zahid zahir zahoor zaina zainul zakaria zaki zakia zakir zakiya zalak zami zamir zangmo zankhana
zapuvise zareen zarina zarine zarir zasivi zayaan zayd zayn zeba zeel zeenat zeenath zeenia
zeeshaan zeeshan zeferino zehaan zehra zeliang zerbanoo zesan zeyaan zhabu zia zian ziaul zinat
zirsangzela zivaan zodinpuii zohra zonunsangi zopa zoramthanga zoravar zoroaster zosangliani
zothanpuia zothansanga zuala zuali zubaida zubaidah zubeen zubeida zubin zuhair zulekha zulfiqar
zunaira
"""
