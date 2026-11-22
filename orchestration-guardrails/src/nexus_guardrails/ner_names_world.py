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

"""Extra given names for PII detection: rest of the world (data only, casefolded, packed).

English, European, Slavic, Latin American, Arabic, Persian, Turkish, Hebrew, East and
Southeast Asian and African given names, on top of the knowledge-graph given names.
``AMBIGUOUS`` holds names that are also ordinary words: they count inside a multi-word name
("Jade Okafor") but never alone.
"""

from __future__ import annotations

# Given names (not already in the knowledge-graph lexicon).
PACKED = """
aada aaliyah abdelaziz abdelhamid abdelilah abdelkader abdelmalek abdelrahman abdi abdirahman
abdirizak abdiwali abdulaziz abdulkadir abdulkarim abdullahi abdulrahman abena abiola abla abshir
abubakar achieng adalynn adanma adanna adaobi adaugo adekunle adel adela adelyn ademola adenike
adeola adesola adesuwa adeyemi adhiambo adjoa adongo adrián aduke adunni adwoa afi afua agustina
agustín agyeman ahmadreza aikaterini ailsa ainhoa aishah akari akhona akinola akinwale akos akosua
akoth akua akwasi alannah alastair alberto aldo aleksi alemayehu alessia alexandar algernon alicja
aline alireza alisa alistair aliza allyson almaz alperen alva amadeo amahle amaia amani amarachi
amare ambrogio ameera amel aminah amine aminu amirhossein amr amélie anathi anaïs andile andrey
andré andréa andréia andrés anele anezka anfisa angelika angelita angharad aniko anikó anne-marie
anneke annemarie anni anselme antoni antonina antonis antti antun anya anyango aoi aphiwe apichart
apirak apiyo apostolos araba arabella araminta arash archibald arda ariana armand armin arnel
arnoldo aroa arpad arseny artemis arthit artyom asahi asanda asemahle ashlee asil asli asmaa asmae
asuka ata athena athina atieno ato attilio audra augustus auma aurelien avi avigail avner avraham
awino ayabonga ayanda ayane ayele aylin ayman ayo ayomide aysha ayunda ayşe azadeh azar azizah
azlan azman azusa aðalsteinn babak babalwa babatunde bader baffour bahar bahareh bahram bakari
baltazar balázs bamidele baraka barasa barbie barbora baris barnaby bart bartholomew bartlomiej
bartolomeo barış bassam bastien bathsheba batsheva batya bautista beathag behnam behrouz behzad
bekele bello benedek benedetto bengt benigno benoît bente berhane berit berk bernardo berta bertram
bettina beyza bheki bimpe binbin biniam binyamin birgitte birtukan bisi bjarni bjoern björk björn
bjørn bo-gum bo-mi bo-ram boaz bogum bohdana boitumelo bolaji bongani bontle boram borys botond
boyu bożena božidar brahim branka braulio brayan brennan bridie brielle bronwyn bryn btissam buhle
bukola bulelwa buse byung-hun byunghun béla cahya cai callan calum camelia campbell cansu carlotta
carmelita carmine casimiro catarina cathal catrin catriona cebile cecilie celestino cengiz ceren
cerys chae-won chae-young chaewon chaeyoung chaim chaimae chaiwat chan-yeol chana chanyeol chara
charalampos chatchai chebet chelimo chemutai chenxi chenyu chepkoech chepngetich cherono cheruiyot
cherylyn chi-ho chi-hung chi-keung chi-kin chi-ming chi-wai chibuike chidiebere chie chigozie
chihung chijioke chika chikeung chiming chinatsu chinelo chinwe chinyere chisom chiwai chloé
chokchai christiane christoffer christoforos chrysa chrysanthi chuka chukwuma chul-soo chulsoo
chun-ho chun-kit chun-wai chun-yin chunhua chunmei chunwai cian cihan cillian cipriano citra claus
clelia clemente cleo clive cláudia clémence conceição concetta constantin corazon cordelia corina
corinne cornelis cosimo costanza cressida crispin cristhian cristiano cruz csilla cuthbert czeslaw
cédric céline cătălin da-hye dae-sung daesung daeun dafni dahabo dahlia dahye daiana dalal dalia
dalila damilare damilola damla dandan danica daniil danil dante danuta danylo dapo darko darragh
darya dat davor dawid dawit debora decha dede dedi defne deivid deji demelza demetrio deqa dereje
dermot derya desmond despina desta dewa diarmuid diep digby dilek diletta dimas dimitris dindo
dineo dinh dino dionisio dionysis ditte divina dmytro do-yoon domagoj dominik donato dong-gun
dong-hyun dong-min dong-wook donggun donghyun dongliang dongmei dongmin dongwook donnacha donya
dorina doron dov doyoon dragana drazen driss drusilla dudu dumisa dumisani duncan duvan duygu dušan
dániel dávid dănuț ebba ebele ebenezer ebo ebru ebuka ece edeltraud edie edmundo edoardo edson eero
efe effie efia efrain efrat efren efstathios egbert egon eiko einat eira eirik eiríkur eitan eithne
ejike eka ekua elad elfriede elham eliezer elio elior elisabet eliseo elizaveta elpida elspeth
elvira elísabet ema embla emebet emelyan emese emiliano emirhan emmanouil emrys endang endre ennio
epifanio erdem eren erich erkan erlendur erlinda erna erno ersin erzsebet erzsébet esi esmee espen
estela estrella ettore euan eugen eugenie eugenio eun-bi eun-woo eunbi eunji eunwoo euphemia
eustace evangelia evaristo evdokia eveliina everton evgeni evgenia evi evie eyob eyþór ezequiel
ezio faber fabiana fabián fabrice fabricio fadi faduma fadumo fahd fajar fani farhiyo faridah
farrah farshid farzad fasika fatemeh fatiha fatim fatimah fatma fatuma faustino fausto fawaz
felicidad fengying fenna ferdinand ferenc fereydoun fergus fezile ffion fiifi fikru filip filippos
fintan fionn fionnuala fiorenzo firas fitria fitzgerald flavio flemming flordeliza florencio
florentina floris flávio folarin folasade fotini fouad fran franca francisca franciszek františek
françois françoise freddy frederik fredy frehiwot fritz friðrik frode froso fruzsina frédéric
fulvio fumi funmi funsho furaha furkan fábio gaetano galih galini galit garba gaspard gavriil gaël
gbenga geir genaro genet geneviève gennaro georgiana georgina georgy gerasimos gerd gerda gergely
germán gerrit gerson gertrud getachew gethin geza ghada ghasem ghassan ghazal ghislaine ghizlane
gi-taek giada giancarlo gianfranco gijs gil gila gilad gilda ginevra gino giorgos giovanny girma
giselle gitaek githinji gitte giuseppina gizella gizem gleb glyn gokhan golnar golnaz gordana
grayson graziano graziella grażyna gregoire gregorio griselda gro grégoire guangming gudmund guido
guinevere guled gulsen gunilla gunther guo guoqiang guro gustave guus guðmundur guðrun gyula györgy
gábor gökhan gülşen günter günther ha-joon ha-yoon hadas hadiza haeun hafid hafiz hafsat hafþór
haifeng haile hairul haiyan hajar hajnalka hajoon halil halima halimah halimo halvor hamad hamda
hamidreza hamisi hamisu hanako hang hanife hanne hanneke hanqing hanwen hanyu haoming haonan haoran
haotian haoxuan haoyu haregewoin harumi harun hasnah hatem hatice hauwa havva hawa hayoon hazem
haziq hedvig hedwig hee-jin hee-young heejin heeyoung hein helle helmi hendri hengameh henk henok
henri henrique henryk hera heriberto hermann hernando heru hervé hesam hessa hester hesti hicham
hideo hien hilario hilde hillary hillel himari hinata hiroyuki hisham hitomi hiwot hjörtur hlengiwe
ho-ming ho-seok ho-yin hodan hoi-lam hoi-yan hok-yin homa homing hongbo hongjun hongmei hongwei
hongyan honoria honorio horatio horia hosein hoseok hossein houda hoyin hrafn hrvoje hryhoriy huda
huifang huiling huimin huizhen humphrey hunor huseyin huyen hyacinth hye-won hyejin hyewon hyo-jin
hyojin hyun-ah hyun-jin hyunah hyung-sik hyungsik hyunjin hyunwoo håkan héctor hélène hülya ibolya
ibukun ichika idan idil idit idowu idriss idunnu ifeanyi ifor ifrah ifunanya ignazio ihor iida
ijeoma ika ikmal ikran ilan ilana ileana ilenia ilham ilias ilkka ilona imad imane imani imelda
immacolata imre inbal ineke inez inge ingebjorg ingvar inmaculada inés inês iona ionela ionuț iosif
ipek irem iren iria irini irish irmgard iryna irén isa isamu ismael ismi isobel istván itai itamar
itsuki iulian ivica iván iwan iyad izzat jabulani jac jacobus jacopo jae-hyun jae-won jae-woo
jaehyun jaewon jaewoo jairo jamileh jamilu jana janie jannie jari jarle jarmila jaroslaw jarosław
jarryd jassim javad jaxson jayson jean-baptiste jean-claude jean-francois jean-luc jean-marc
jean-michel jean-paul jean-philippe jedediah jefferson jeison jelagat jelle jemima jenifer jenson
jepchirchir jepkosgei jericho jeronimo jesús jhon jhonatan ji-an ji-eun ji-hun ji-hye ji-su ji-sung
ji-yu jiahao jiahui jiajia jiale jiaming jiao jiawei jiaxin jiayi jide jieun jihad jiho jihoon
jihun jihye jimin jin-woo jin-young jinfeng jinglei jingwen jingxuan jingyi jinho jinlong jinwoo
jinyoung jinyu jira jiraporn jisu jisung jitka jiwoo jiyeon jiyu jiří joana joaquín joerg johana
johann jolien jomar jonatas jonel jong-hyun jonghyun joo-won joong-ki joongki joonho joowon joris
josefa josephina josiah jostein josue josé jovan joão joël juancarlos juanpablo judit juha jukka
julianna juliano julieta julián jumana jun-seo junfeng jung-ho jung-kook jung-min jung-woo jungho
jungkook jungmin jungwoo junhao junjie junjun junko junlin junming junseo junwei junyi jurriaan
justyna juthamas jutta juvy jytte jérôme jéssica jón józsef jörg jørgen jürgen ka-chun ka-hei ka-ho
ka-ki ka-lam ka-lok ka-man ka-ming ka-po ka-shing ka-sing ka-tsun ka-wai ka-yan ka-yee kaan kabelo
kabiru kachun kadir kagiso kaho kaia kaisa kaitlin kaiwen kaixuan kaiyue kalle kalliopi kalman
kalok kaman kamel kaming kamolwan kanako kanchana kannika kanokwan kanya karabo karanja kareem
karel karianne karima karol karoly kasem kashing kasumi katarina katayoun kateryna kathrin katja
katlego katrin katrín kaveh kawai kawthar kayan kaylee kazuko kazumi kazuya keamogetse kebede kees
kehinde keita keke kelechi kemi kene kenechukwu kenza kerem keren kesorn keziah kgomotso khadijah
khadra khai khairul khoa khrystyna khulekani ki-bum ki-tae kian kibet kibum kidist kien kiera
kikelomo kimani kimiko kimutai kin-wah kinwah kioko kipchoge kipkemboi kiplagat kiprop kiprotich
kipruto kiptoo kirsty kit-ying kitae kittisak kiyoko klara kleber kleopatra kobina koharu koji kojo
konstantina koray korkor kornel kosei kosisochukwu kostas kostya kotone kouki kourosh kresimir
krista kristie kristijan kristine kristján krisztian krisztina kritsada krystyna kulap kun kunle
kurniawan kwadwo kwaku kweku kwesi kwok-keung kwok-leung kwok-wai kyalo kylie kyoko kyriaki
kyriakos kyu-hyun kyuhyun kyung-hee kyunghee kyungsoo kári kübra ladan lais lajos laleh lamai
lamberto lambrini lancelot langlang lanre lanying larbi larysa lateefa latifa latifah laurentiu
lauri lautaro lavinia lawal lazar lazaro lefteris leidy leifur leke lemlem lemma lennart lenuta
leone leonel leonidas leopold leopoldo lerato lestari lesya lethabo letitia letizia letícia levent
leyla lia liat liban lidia lies lieselotte lihi liisa lijuan lijun lili lilian liliana liliane
lilla lilly limei liming limor lindani lingling linlin lior liora liqiang lisandro lise lito liubov
liudmyla liv livio liviu liwei lixin liyan liying liza llewelyn llinos loc loes lok-man londiwe
lorcan loredana loris lotte louay loubna loïc luan lubov lucien lucienne lucija lucila lucio lucius
lucía ludmila ludvig ludwig luisa luiza lukman lukáš lulwa luminita lunga lungelo lungile lupita
luuk luyanda luz luzviminda luíza lwazi lykourgos lászló lăcrămioara maaike maame macario macharia
maciej maddalena mads magda magdolna magnús mahdi maher mahmud mahmut mahnaz mahsa maicon maina
maire mairead mairi maisie maitha majda majed makar makhosi maksym malee malena malthe mamello
mamoun man-ho man-kit man-wai man-yee manabu manal manh manit manolis mansour manyee mara maral
marcin marcos margarete margarida margherita margreet mariane mariangela maribel maricel
marie-claire marie-france marie-louise mariela marigold marijke mariko marilou marino marissa marit
marites marius mariusz marja marjan marjolein marketa markku marlowe marmaduke marsha martyna
martín maryan maryluz maryna maría masahiro masashi masego masoud masoumeh massimiliano mastura
mateus mateusz matheo mathilda mathis mathéo matija matilde matti matvey mauro mawar maxim maximo
maysoon mayu mayuree mazen małgorzata mbali mbuso mduduzi mechthild mees mega mehran mei-ling
mei-yee meihua meili meiling meir meirav meixiu mekdes mekonnen melaku melati melchor melek melike
melina menachem mengyao mensah merav merel meriem meron mert merve meryem meseret metin meytal
mhairi mi-rae mi-young michaela michalis michaël michał mickael mihajlo mihaly mihăi mikayla mikkel
mikko mikolaj milad milena millicent miloš miltiadis mimi mimoun min-hyuk min-kyu min-seo min-soo
minenhle mingjie mingliang mingxuan mingyu minho minhyuk minji minjun minkyu minna minnie minseo
minsoo mio miodrag mirae mireille mirela mirjam mirjana miron miroslaw mirto mishal mislav mitsuo
miyoung miyuki mizuki moataz moe mohammadreza mohamud mohsen mojgan mojisola momoka mondli montague
mordechai moremi morenike moritz morteza mortimer morwenna moshe mostafa mounir mourad mouza mpho
mpumelelo msizi mstislav mthunzi mueni muhd muireann mulugeta mumbi muna mungo murad musa mustapha
musyoka mutaz muthoni mutua mwanaisha mwende mykhailo mylene myroslava márcio mélanie mónica mônica
müge müller mădălina na-yeon nada nadav nadege nader nadiah nafsika naftali nahla najib najla
naledi nam-joon namjoon nanako nandi nandipha nandor nanna napapat napat narges narong nasra nastya
natan natasa nathalia natsumi nattapong nattawut nattaya natthida nawaf nayeon nazanin nazar
nazario nazli nazri ndinda nduku necati nechama neda neema negar negash nele nello nenad nenita
nerea nerissa neslihan nestor neta neven neville nga ngai-lam nghia nhan nhi nhlanhla nia nicanor
nicha nicolae nicolai nicoletta nicoline nicolás nienke nii nika niki niko nikolaj nikolett nikos
nilo niloofar nimco ningning ningsih nir nitipong nittaya nives niyi nizar njabulo njoroge nkem
nkiru nkosana nkululeko nnaemeka nneka nneoma noam nobuhle nobuo nobuyuki noe noelia noelle noemi
noga noi nok nokuthula noluthando nolwazi nomalanga nombuso nomsa nomusa nongnuch nonhlanhla noora
noraini norazlina norberto norhayati nosipho noud noura noureddine novak novi noémie noë nqobile
nthabiseng ntombi ntombizanele ntombizodwa nuala nuhu nujood nuno nunzio nur nurfarah nurhayati
nuri nurit nyambura nyokabi oana oanh obadiah obiageli obiora oceane ochieng octavia octavian
octavius océane odhiambo odon odysseas ofelia ofentse ofer ogechi ohene oi-ling okechukwu okey
okoth okta ola olabisi olajide olakunle olalekan olamide olanrewaju olatunde olatunji olawale
olegario oleh oleksandra olha olimpia olivera oliwia olle olli olu oluchi oluwatobi oluwole omari
omid omolara omolola omondi omotayo omotola omowunmi omri ondřej onesimo onur onyango onyeka
onyinye oonagh ophelia ophelie orapin orazio oren oreste orestis orhan orit orla ornanong orsola
orsolya osama osei osnat osvaldo oswaldo ottavio otávio outi owino oyvind ozan ozlem pailin pairoj
paislee pak-hei pak-ho pakorn palesa pancho panos pantelis panya paraskevi parsa parvaneh pascual
pasquale patchara patcharee patrik patrizia patrycja patryk patrícia paulette paulina paulo paweł
payam pegah peiyi pekka pengfei pensri percival peregrine periklis pernille persefoni persephone
petri petronella petros petru peyman peyton phat philipp philippa phong phuc phumzile pichai piera
pierre-yves piers pim pimchanok pimpa pinar pio pirjo pitak piyada pnina poku polat poliana
pongsakorn pooneh porfirio portia poul pouya praewa prakit pranee prasert praskovya prayut preben
predrag preecha primrose priscila pui-yee pulane puspita putra pyotr péter qhawe qianqian qiaoling
qingyun qiuping qiuyue quoc quyen rabab rabi rabiu rachelle rachid radka radosław radovan raed
rafaela rafaelito rafal rafał raffaella rafferty ragnhild raha rahayu rahmawati rajae ramazan ramil
ramin ramy ramzi ramón randi ranim ranulph raphaël rashidi ratana rattana rattiya rawan rayan razak
razali raúl recep reda rediet redouane refilwe refugio rehema reidun reina reitumetse remus renato
rendra rens renske rené renée rethabile retno reuben reuven revital rey reynaldo rezso rhiannon
rhodri rico rigoberto riikka rika rikako riki rikke riku rimma rini risto rivka riyad rizki robbert
rodel roderick rodica rodion rodolfo rodolphe rogerio rohana roko rolly romane romeo romina rommel
ronaldo ronen rongrong ronit roos rosalia rosamund rosaria rosemarie rosli rosnah rossella rotimi
rouba roula roxana roya ruairi ruaridh ruba rubén rudi rufino ruihan ruiqi ruixin rukayya rula
rully runze ruoxi ruoyu ruqiya ruzica rylee ryoko ryuji ryunosuke régis réka rémi rúben rúnar
răzvan saba sabino sadegh sae safaa sagal sahra saja sakchai sakiko salamatu saleh salih salmah
samanta samer samsam samu samy sanae sanaz sander sandi sandile sandor sandro sanele sang-hoon
sang-min sang-woo sanghoon sangmin sangwoo sani sanja sanna santo saowalak sappho sarawut sarpong
sasha sasithorn saskia sathit satomi sau-ling saud saul saverio savva sawsan sayuri sbongile
sebastián seda seiji selam selamawit selina selma selvaggia sem sema semyon sena senait senzo
seo-jun seojun seok-jin seokjin seoyeon seoyun seraphina seren sergiu serhiy serwaa setareh
seung-gi seung-hyun seung-woo seunggi seunghyun seungwoo severiano sevgi sevim sewa seyi seymour
sfiso shadi shahd shahla shahram shai shaikha shaima shams shani shanshan sharifah shatha shaul
shawna shehab shehu sheida sheikha shelly sheng shiela shimon shingo shira shiri shiro shizuka
shlomo shmuel shoichi shona shuai shuang shuhui shuichi shuk-fan shunsuke shuxin shuyi si-woo
siamak sibel sibilla sibongile sibusiso sicheng siegfried sieglinde sif sigal sigge siggi signe
sigríður sigurd sigurðr siham sihan silvestre silvio silviu simge simin simisola simiyu simón
sin-yi sinan sinazo sindisiwe sindre sinidu sinta siphokazi siqi sirad siri sirikit sirinya
siriporn siu-fung siu-lung siu-ming siu-wing siu-yan siuming sivan siwaporn siwoo sixten siyabonga
siyu sizakele sladjana slamet slavica slobodan smadar smaragda smaranda snežana snorri so-hee
so-yeon sofiane sofie sofya sofía sohee soheil solana solange solomiya solomon somayeh sombat
sombun somchai somporn somsak somsri somto songkran sonja soo-ah soo-young sooah soojin sooyoung
sorcha sorina sotiria sotiris souad soudabeh soufiane soukaina soyeon spartak srdjan stavroula
stefanie stefán stein stelios sterre stevie stijn stina stipe struan sture stéphane stéphanie
su-bin suad subin subira sucaad suchart suda sudarat sugeng suha suhaila suharto suk-yee sukarno
sulafa sulaiman sulastri suleiman suleyman sum-yi sumalee sumaya sumeyye sumire sun-hee sunan
sung-ho sung-hoon sung-jin sungho sunghoon sungjin sungmin sunhee sunisa supansa supaporn supattra
supriyadi surachai sureeporn susana susanna susanti susilo susumu sutthipong suwanna suzu svante
sveinn svend svitlana svyatoslav syafiq syahmi sylwia synnove sze-man szilard szilvia sándor sævar
ségolène sérgio sílvia sónia søren sławomir tadeo tadesse tae-hyung tae-min tae-yang taehyung
taemin taeyang tahereh taichi taiga taiwo tak-ming tak-wah takako takayuki takuya talal talia
tamaki tamar tamrat tamsin tamás tanawat tanja tapani tarek tarik tarquin tasoula tatiane tatsuya
tawfiq tayla tayo tebogo teerapat tefera tegwen tehila teodor teodoro teresita terje tesfaye tessie
tetiana thabiso thaddeus thais thalia thanakorn thanasis thanawat thandeka thandi thandiwe thando
thang thanida thanut thawatchai thaís thembeka theodora theofilos thidarat thien thinh thira
thorbjorn thorkild thuong thérèse tian tianyi tianyu tibor tiburcio tigist tihomir tiina tijjani
tijn tilly timea timo timoteo timothee timothée tin-yau tineke tingting tipawan tirunesh tirza
titilayo tiziana toan tobi tochukwu toktam tomer tomomi tomos tomás tomáš tonyo torbjorn toribio
torquil torunn tosca tosin tossapol toyin traudl triana trinh trofim trond trong truong tryfon
trygve trystan tsehay tshepo tsukasa tsun-yin tsuyoshi tsz-ching tsz-hin tsz-kin tsz-wing tszching
tszhin tszwing tudor tugba tumaini tuomas turgut turid turki tuti tuula tuva tuyen tuğba tyra tzipi
tzipora tzvi tânia tímea ubah uche uchechi udom ugo ugochukwu uju uliana ulises ulomma ulrik ulrika
ulyana ulysse ulysses umberto umut unathi upendo urbano uri usama utami ute uyen uzoamaka vadim
vahid valdemar valdimar valentine valentyna valeri valeria valter valérie vanesa vangelis vanna
varda varvara vasileios vasiliki vasilisa veera vega vegard venancio venetia verena vergel veronika
vichai vida vidar viktoria villads ville vilma vilmer vilmos vinko vinícius viorica visnja vitaliy
vitaly vito vittorio vitória viviane vlad volkan voula vsevolod vuk vusi vuyani vuyo václav
véronique víctor wael wafaa wafae wafula wagner wahyuni wai-chun wai-hung wai-kit wai-ling wai-man
wai-shan wai-yin waiman wairimu waldemar wambui wanchai wanjiku waraporn warsame wassana wawan
wayan weerasak wekesa wenceslao wenhao wenjing wenjun wenting wenxuan weronika wessel wichai widad
widya wiebke wiktor wilai wilfredo wilfried wilhelmina willem wilmer wilson wing-chun wing-hang
wing-kei wing-kit wing-lam wing-sze wing-tung wing-yan wing-yee wingkei wingyan wirat witold
wladyslaw woo-sik woojin woosik worawut worknesh wulan wuraola xanthi xenofon xiangyu xiaobo
xiaodong xiaofeng xiaogang xiaohong xiaojun xiaoli xiaoling xiaolong xiaomei xiaoming xiaoping
xiaoqing xiaotian xiaowei xiaoyan xiaoyu xinhui xinran xinyu xinyue xiuying xolani xolile xuan
xuanyi xuefeng yaa yaakov yacoub yael yaffa yagazie yago yahia yahir yahya yakov yakubu yalda
yamato yamila yamkela yan-tung yan-yan yaniv yanting yao yaowalak yaqi yarden yared yasaman yaser
yasmina yassine yasuhiro yasuo yat-ming yat-sen yawen yaxin yazan yazid yağmur ye-eun ye-jun ye-rin
yee-ling yee-man yeeman yeeun yeferson yehuda yehudit yeison yejin yejun yemi yerin yesenia yesica
yessica yetunde yevhen yewande yichen yifan yigit yihan yildiz yilin yiming ying-chi ying-kit
ying-ying yining yinka yitzhak yiu-man yiu-wai yixuan yiğit ylva yocheved yohannes yomi yonatan
yonela yongyut yonit yoo-jin yoojin yoon-gi yoon-seo yoongi yoonseo yordanos yosef yoshihiro
yoshiki yoshio yossi younes young-hee young-jae young-soo younghee youngho youngjae youngsoo yu-ri
yuanyuan yuchen yudi yue yueyue yuhan yui yuichi yuji yuk-fai yuk-ling yukari yuko yuliana yuna
yunfei yuni yuqi yurika yuriy yury yusei yuting yutong yutthana yuxin yuxuan zacarias zacharias
zafer zainal zaira zakari zakhar zalina zama zandile zawadi zayed zaynab zdenka zdeněk zdravka
zdravko zdzislaw zebedee zeev zehava zeina zeinab zena zenebech zeno zenobia zenon zerihun zethu
zeynab zhao zhengyu zhenhua zhihao zhiming zhiqiang zhiwei zhiyuan zhongwei zhu zhuo zhuoran ziad
zihan zihao zihui zikhona zimkhitha zimo zinaida zineb zinhle zinnia zinovy zintle ziqi zita ziv
zixin zixuan ziyi ziyu zlatan zodwa zohar zohreh zoltán zoraida zorana zorica zoé zoë zsolt zsombor
zsuzsa zsófia zubairu zuhura zukisa zulai zulkifli zuwaira zuzanna zvonimir zygmunt ádám ágnes ákos
álex álvaro ángel árpád ásdís åge åsa åse çağlar élise éloïse émilie éva ísak ólafur ömer özge
özlem ørjan øyvind þorsteinn þór þórdís đorđe đurđa łukasz şeyma şükrü štěpán željko ștefan
ștefania
"""

# Also ordinary words: multi-word names only.
AMBIGUOUS = """
aby adit akin alin ally anam anan anis atta ayu babloo bablu babu baby bas begum bela bibi bing
blas bobo bode bong bora bose bree bubby chai cherry chi chinky da dang daud deb deep dele desi
dhan dimple dola dolly dong edit fakir flora fu gabi gad ganga geo goldy gora gugu gul guru hakim
hala hamlet happy harm heer hind hop ife iva jama jami joke jolly juniper kaiser kala karma kiki
knut koel lam lama lech lev lien lina line linn lino loan lone love lovely lu lucky ly lyra maha
maki mate meet meng mila mina mirza mou mu munshi muse naa naif nan nana nawab ni noa noble odd om
omer oz pal pandora papa pia piet pinky prince qi quan rais raja ran reem rhea rim rima rinku roi
roxy rune rupa sade sahib sai said sang serenity shade shakti shi shine shiny sho sika sina smit
soli sultan sultana sunny taha tai taj tal tala tamer tan tansy tine tinku titi tolu tone tong tore
toru tu tuba tung twinkle vasu veer verity vina viral vu vy wale wali wan wanting wing wu wyn xu
yair yam yati yaw yen yin yoga
"""
