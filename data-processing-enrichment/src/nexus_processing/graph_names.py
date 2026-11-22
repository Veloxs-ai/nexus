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

"""Given names for text entity typing (data only, casefolded, packed).

About 3,000 given names from English, Indian, Hispanic and Lusophone, European, Slavic,
African, Arabic, Persian, Turkish and East Asian naming traditions. Packed as one
whitespace-separated string; ``graph_lexicon.given_names()`` builds the set on first use.
``AMBIGUOUS`` lists names that are also ordinary words or places: they type a two- or
three-word span ("Grant Hill") but never a lone capitalised word ("Grant").
"""

from __future__ import annotations

PACKED = """
aaron abby abel abigail abraham ada adam addison adele adeline adrian adriana adrienne agatha
agnes aidan aiden aileen aimee alan alana albert alberta alec alejandra alejandro alexa alexander
alexandra alexandria alexis alfie alfred ali alice alicia alina alison alissa allan allen allison
alma alvin alyssa amanda amber amelia amelie amy andre andrea andreas andrew andy angel angela
angelica angelina angie anita ann anna annabel annabelle anne annette annie anthony antonia
antonio april archie arianna ariel arlene arnold arthur ashley ashton aubrey audrey austin ava
avery barbara barry beatrice beatrix becky belinda bella ben benedict benjamin bernadette bernard
bernice bert bertha beth bethany betsy betty beverly bianca bill billy blake blanche bob bobby
bonnie boris brad bradley brady brandon brandy brenda brendan brent brett brian briana brianna
bridget brittany brooke bruce bryan bryce byron caleb calvin cameron camila camilla candace
cara carl carla carlos carly carmen carol carole caroline carolyn carrie carter casey cassandra
cassidy catherine cathy cecil cecilia cedric celeste celia chad chandler charity charlene charles
charlie charlotte chelsea cheryl chester chloe chris christian christie christina christine
christopher christy cindy claire clara clarence clarissa claude claudia clay clayton clifford
clint clinton clyde cody colby cole colin colleen connie connor conor constance cora corey
cornelius courtney craig cristina crystal curtis cynthia daisy dale dallas dalton damian damon
dan dana daniel daniela danielle danny daphne darcy darius darlene darnell darren darryl dave
david dawn dean deanna debbie deborah debra declan dee deirdre delia della delores denise dennis
derek derrick desiree devin devon dexter diana diane dianne dick diego dillon dolores dominic
dominique don donald donna donovan dora doreen doris dorothy doug douglas drew duane dustin
dwayne dwight dylan earl ebony ed eddie edgar edith edmund edna eduardo edward edwin eileen
elaine eleanor elena eli eliana elijah elisa elise eliza elizabeth ella ellen ellie elliot elliott
eloise elsa elsie elton emanuel emerson emil emilia emily emma emmanuel emmett erica erik erika
erin ernest ernestine esme essie estelle esther ethan ethel eugene eunice eva evan evangeline
eve evelyn everett ezra fabian faith fay felicia felicity felix fern fernando fiona florence
floyd flynn forrest frances francesca francis francisco frank frankie franklin fred freddie
frederick freya gabriel gabriella gabrielle gail garrett garry gary gavin gemma gene geneva
genevieve geoffrey george georgia gerald geraldine gerard gertrude gideon gilbert gillian gina
ginger gladys glen glenda glenn gloria gordon grace gracie graham grant greg gregory greta
gretchen griffin gwen gwendolyn hailey hal hank hannah harley harold harriet harrison harry
harvey hayden hazel heath heather hector heidi helen helena henrietta henry herbert herman holly
hope horace howard hubert hudson hugh hugo hunter ian ida imogen ines ingrid irene iris irma
isaac isabel isabella isabelle isaiah isla ivan ivy jack jackie jackson jacob jacqueline jade
jaime jake james jamie jan jane janelle janet janice janine jared jarrod jasmine jason jasper
javier jay jayden jean jeanette jeanne jeff jeffery jeffrey jenna jennie jennifer jenny jeremiah
jeremy jerome jerry jesse jessica jessie jill jillian jim jimmy jo joan joann joanna joanne
jocelyn jodi jody joe joel joey johanna john johnathan johnny jon jonah jonathan jordan jorge
joseph josephine josh joshua josie joy joyce juan juanita judith judy jules julia julian juliana
julie juliet june justin justine kaitlyn kara karen kari karl karla kate katelyn katherine
kathleen kathryn kathy katie katrina kay kayla keira keith kellie kelly kelsey ken kendall
kendra kenneth kenny kent kerry kevin kim kimberly kirk kirsten kristen kristin kristina kristy
kurt kyle lacey lana lance landon lara larry laura lauren laurence laurie lawrence leah lee
leigh leila leland lena leo leon leonard leonardo leonora leroy leslie lester levi lewis lexi
liam lila lillian lily lincoln linda lindsay lindsey lionel lisa lloyd logan lois lola lonnie
lora loretta lori lorna lorraine louis louisa louise lucas lucia lucille lucinda lucy luis luke
lydia lyle lynda lynn mabel mackenzie madeleine madeline madelyn madison mae maggie malcolm
mallory mandy marc marcia marcus margaret margarita margie maria marian marianne marie marilyn
marina mario marion marjorie mark marlene marshall martha martin marvin mary mason mathew matt
matthew mattie maureen maurice max maxine maxwell may megan meghan melanie melinda melissa
melody melvin mercedes meredith mia micah michael michele michelle mickey miguel mike mildred
miles millie milton mindy miranda miriam misty mitchell molly monica monique morgan morris
muriel myra myrtle nadia nancy naomi natalia natalie natasha nathan nathaniel neal ned neil
nell nellie nelson nettie nicholas nick nicky nicola nicole nigel nina noah noel nora norma
norman oliver olivia ollie opal orlando oscar otis owen paige pam pamela pat patricia patrick
patsy patty paul paula pauline pearl peggy penelope penny percy perry pete peter phil philip
phillip phoebe phyllis piper polly preston priscilla quentin quincy quinn rachael rachel
ralph ramon randall randy raquel ray raymond reba rebecca reed regina reginald reid rena rene
renee rex rhonda ricardo richard rick ricky riley rita rob robbie robert roberta roberto robin
robyn rocky rod rodney roger roland ron ronald ronnie rory rosa rosalie rose rosemary ross
rowan roxanne roy ruby rudy rufus rupert russell ruth ryan sabrina sadie sally sam samantha
samuel sandra sandy sara sarah savannah scarlett scott sean sebastian selena seth shane shannon
sharon shaun shawn sheila shelby shelley sheri sherry shirley sidney sienna silas simon
skylar sofia sonia sonya sophia sophie spencer stacey stacy stanley stella stephanie stephen
sterling steve steven stewart stuart sue summer susan susanne suzanne sybil sydney sylvia
tabitha tamara tammy tania tanya tara taylor ted teddy terence teresa teri terrance terrence
terri terry tess tessa thelma theo theodore theresa thomas tiffany tim timothy tina toby todd
tom tommy toni tony tonya tori tracey traci tracy travis trent trevor tricia trinity tristan
troy trudy tyler tyrone ursula valerie vanessa vaughn velma vera verna vernon veronica vicki
vickie vicky victor victoria vince vincent viola violet virgil virginia vivian wade wallace
walter wanda warren wayne wendell wendy wesley whitney wilbur wilfred will willa william
willie willis wilma winifred winston wyatt xavier yolanda yvette yvonne zachary zack zane zelda
zoe zoey
aarav aarti aashish abhay abhijit abhinav abhishek aditi aditya advait ajay ajit akash akhil
akshay alok aman amar amit amita amol amrita anand ananya anil anirudh anita anjali ankit ankita
ankur anshul anu anuj anup anupam anurag anusha aparna archana arjun arnav arpita arun aruna
arvind asha ashish ashok ashwin atul avinash ayesha ayush balaji bharat bhavana bhavna chandan
chandra chetan chitra deepa deepak deepika dev devendra dhruv dilip dinesh divya durga gaurav
geeta girish gita gopal govind hari harish harsh harsha hema hemant indira ishaan ishita jagdish
jaya jayant jitendra jyoti kamal kamala karan karthik kartik kavita kavya keshav kiran kishore
krishna kunal lakshmi lalit lata madhav madhu madhuri mahesh malini mamta manish manisha manoj
meena meera megha mohan mohini mukesh murali nadeem naina nandini naresh naveen neelam neeraj
neha nikhil nikita nilesh nirmala nisha nitin pallavi pankaj parth pooja poonam prabhu pradeep
prakash pranav prasad prashant pratik praveen preeti prem priya priyanka puja rachna radha
radhika raghav rahul raj rajan rajat rajeev rajendra rajesh raju rakesh ram raman ramesh rani
ranjit rashmi ratan ravi rekha renu reshma ritu rohan rohit roshan ruchi sachin sagar sahil
sakshi sameer samir sandeep sangeeta sanjana sanjay sanjeev santosh sapna sarita satish saurabh
seema shalini shankar sharad shashi sheetal shilpa shiv shivani shobha shreya shruti shubham
shweta siddharth smita sneha sohan sonal sonali srinivas subhash sudha sudhir sujata sumit
suman sunil sunita supriya suraj surendra suresh sushant sushil swapna swati tanmay tanuja
tanvi tarun tushar uday uma umesh usha utkarsh vaibhav vandana varun vasant venkat vidya vijay
vikas vikram vimal vinay vineet vinod vipin vishal vivek yash yogesh zoya
abdul abdullah adnan ahmad ahmed aisha akram ali amina amir amira anwar asif aziz bilal faisal
farah farhan farid fatima fawad habib hadi hamza hana hani haroon hasan hassan hussain hussein
ibrahim imran iqbal irfan jamal jamila javed karim khadija khalid laila layla mahmoud majid
malik mariam marwan mohamed mohammad mohammed mona mustafa nabil nadia naeem nasir nasser
noor nour omar osman rami rana rania rashid reza saad saeed salim salma sami samira sana
sara shahid shakil sharif tariq usman walid waleed yasmin yasser yousef youssef yusuf zahra
zainab zaid zara zubair darius dariush farzaneh mehdi navid parisa shirin
ahmet ayse burak can cem deniz elif emine emre esra fatih hakan hulya kemal mehmet murat
mustafa ozge serkan selin tolga yasemin yusuf zeynep
adaeze adebayo adewale ama amara amaka ayodele babajide chidi chidinma chiamaka chinedu
chinonso chioma chukwuemeka chukwudi efua emeka femi folake funmilayo ifeoma ikenna kayode
kofi kwabena kwame kwasi ngozi nkechi nnamdi obinna oluwaseun olumide olusegun oluwadamilare
segun tendai thabo themba tunde uchenna wanjiru wangari kamau kariuki mwangi njeri otieno
akinyi zanele sipho lindiwe nomvula busisiwe abebe tsion yonas
abril adolfo agustin aitana alba alejo alfonso alicia alonso alvaro amparo andres angeles
anibal antonia araceli armando arturo augusto aurelio beatriz benito blanca camilo candela
carlota catalina cayetana cesar claudio concepcion consuelo cristian cristobal dario delfina
diego dolores domingo eduardo elena elias eloisa emilio enrique ernesto esperanza esteban
estefania eugenia eva facundo federico felipe fernanda fidel florencia gabino gaspar gerardo
gilberto gonzalo graciela guadalupe guillermo gustavo hernan horacio humberto ignacio ines
irene isidro jacinto jaime javiera jesus jimena joaquin jorge josefina juana julio leandro
leonor lorena lorenzo lucas luciana luciano lupe macarena manuel manuela marcela marcelo
margarita mariana mariano marisol martina mateo matias mauricio maximiliano mercedes milagros
mireia nahuel nicolas nuria octavio olga pablo paloma paola patricio paz pedro pilar rafael
ramiro raul rebeca reinaldo renata roberto rocio rodrigo rogelio rolando rosario ruben salvador
santiago santino sergio silvia soledad tomas valentina valentino veronica vicente ximena
adriano afonso andreia antonio barbara bruna caio carolina conceicao diogo duarte fabio
fabiola filipa flavia gabriela goncalo guilherme gustavo heitor helena joao joaquim jose
juliana larissa leticia luana lucas luiz marcio marta matheus miguel murilo otavio patricia
raimundo renan ricardo rui sebastiao tiago thiago vinicius vitor vitoria
achille adele agnese alessandra alessandro alessio alfredo alice amedeo andrea angelo anna
antonella antonio arianna aurora beatrice benedetta bruno carla carlo caterina cesare chiara
claudio cristina daniele dario davide domenico elena elisa emanuele enrico enzo fabio fabrizio
federica federico filippo francesca francesco franco gabriele giacomo gianluca gianni giorgia
giorgio giovanna giovanni giulia giulio giuseppe ilaria lorenzo luca lucia luciana ludovica
luigi manuela marcello marco mario martina massimo matteo maurizio michela michele mirko nicola
nicolo paola paolo pietro raffaele riccardo roberta roberto rocco salvatore sara serena
silvia simona simone sofia stefania stefano teresa tommaso valentina valerio vincenzo vittoria
adele adrien agathe alain alexandre alexis alice amandine amelie anais antoine apolline arnaud
aurelie baptiste benoit bernard brigitte camille capucine cecile celine chantal charles
christophe claire clemence clement corentin cyril damien delphine denis didier dominique elodie
eloise emile emilie emmanuel eric estelle etienne fabien fabienne florence florian francois
francoise frederic gael gaelle gaston genevieve georges gerard gilles guillaume helene herve
hugo isabelle jacques jean jeanne jerome josephine julien juliette laetitia laure laurent lea
leon leonie loic louis louise luc lucie manon marc marcel margaux marguerite marine mathieu
mathilde maxime michel monique nathalie nicolas noemie odile olivier pascal pascale patrice
philippe pierre quentin raphael remi renaud romain sandrine sebastien serge simone solene
stephane sylvie theo therese thibault thierry valentin valerie veronique victor vincent
virginie xavier yann yannick yves zoe
achim agnes alexander andrea andreas anja anke annika axel barbel bastian benedikt bernd
birgit bjorn carsten christa christoph claudia dagmar daniela detlef dieter dirk doris
elke erik ernst fabian felix florian frank franz frieda friedrich gerhard gisela gottfried
gregor gudrun gunter hannelore hans hartmut heidi heike heinrich heinz helga helmut henrik
herbert hildegard holger horst ilse ingeborg ingo jan jannik jens joachim jochen johannes
jonas jorg jurgen kai karin karl karsten katharina kerstin klaus konrad kurt lars lena lothar
lukas maik manfred manuela marcel margit markus martina matthias maximilian monika nadine
niklas norbert olaf oliver otto petra rainer ralf reinhard renate rolf rudiger rudolf sabine
sandra sascha silke stefan steffen susanne sven thomas thorsten tobias torsten udo ulrich
ulrike ursula uwe volker waltraud werner wilhelm wolfgang
aino anders anneli arvid astrid birgitta bo britt dag einar elin elsa emil erik eva frida
gunnar gustav hakon hanna harald helge henrik hilda ingrid ivar jens johan karin kjell
kristian lars leif linnea magnus maja malin mats mikael nils olof oskar per ragnar sigrid
siv solveig stig sune svea sven thor tor tove ulf ulla viggo vilhelm aksel anette bjarne
camilla dorte freja jesper kasper lasse mette morten rasmus soren tove trine
aart anouk bram daan dirk eline femke fleur geert hendrik ilse jaap jeroen joost koen
lieke maarten marieke niels pieter ruud sanne sjoerd thijs wouter
agnieszka aleksander aleksandra andrzej anna barbara bartosz beata dariusz dorota elzbieta
ewa grzegorz halina iwona jacek jadwiga jakub jan janusz jerzy joanna jolanta kamil
karolina katarzyna kazimierz krzysztof leszek lukasz magdalena malgorzata marek marta
marzena michal monika natalia pawel piotr przemyslaw radoslaw renata roman ryszard slawomir
stanislaw szymon tadeusz teresa tomasz urszula wiktoria wojciech zbigniew zofia zuzana
alena alois bohumil dagmar eliska frantisek hana ivana jaroslav jiri josef katerina
ladislav lenka libor lucie lubos milan miloslav miroslav ondrej pavel pavla petr radek
stanislav tereza vaclav vladimir vojtech zdenek
adrian alexandru andreea bogdan catalin claudiu cosmin cristian dan diana dragos elena
florin gabriel gheorghe ion ioana iulia laura lucian marian mihai mihaela mircea nicoleta
ovidiu radu raluca razvan sorin stefan teodora valentin vasile
agnes andras attila balazs bence csaba dora eszter gabor gyorgy istvan janos jozsef
katalin laszlo marton miklos peter reka szabolcs tamas zoltan zsofia zsuzsanna
aleksandr aleksei alexei alla alyona anastasia anatoly andrei anton arkady artem boris
daria denis dmitri dmitry egor ekaterina elena evgeny fyodor galina gennady grigory igor
ilya inna irina ivan katya kirill konstantin ksenia larisa leonid lyudmila maksim marina
mikhail nadezhda natalya nikita nikolai oksana oleg olga pavel polina roman ruslan
sergei sergey stanislav svetlana tatiana tatyana timur valentina valery vasily viktor
vladimir vladislav vyacheslav yaroslav yekaterina yelena yulia yuri zhanna
andriy bohdan halyna mykola oleksandr oleksiy olena petro stepan taras vasyl volodymyr
yaroslava yuliya
aleksandar biljana bojan branko dejan dragan goran ivana jelena jovana marija marko milica
milos nemanja nikola sasa snezana stefan tijana vesna zoran ante antonija josip luka
mateja matej tomislav vedran zeljko
agathi alexandros anastasios andreas angeliki antonios athanasios christos dimitra dimitrios
eleni evangelos georgios ioanna ioannis katerina konstantinos maria nikolaos panagiotis
sofia spyros stavros theodoros vasilis yiannis
aoife aisling caoimhe ciara ciaran clodagh colm cormac dearbhla deirdre donal eamon eimear
eoin fergal fiachra grainne niamh oisin padraig roisin ronan saoirse seamus sinead siobhan
tadhg una alasdair angus callum eilidh fraser hamish iain isla lachlan morag murdo rhona
alun bethan bronwen carys dafydd dylan eleri emyr gareth geraint gwyneth huw ieuan iolo
lowri meinir owain rhian rhys sian tegan
ai aiko akane akemi akihiro akira atsushi ayaka ayumi chiaki chihiro daichi daiki daisuke
emi eri fumiko hana haruka haruki haruto hayato hideki hikari hina hiroki hiroko hiromi
hiroshi hiroto hisashi ichiro jun junichi kaito kana kaori kaoru katsumi kazuki kazuo kei
keiko ken kenichi kenji kenta kiyoshi koichi kota kumiko mai makoto mami mana mao mari
masaki masako masaru masato masayuki mayumi megumi michiko midori mika miki minoru misaki
mitsuko miyu momoko naoki naomi naoko natsuki noboru noriko osamu reiko ren riko rin
risa ryo ryota ryuichi sachiko saki sakura satoshi sayaka setsuko shigeru shin shinji
shiori shota shun sora sota tadashi takahiro takashi takeshi takumi taro tetsuya tomoko
tomoya toshiko toshiro tsubasa tsutomu yasuko yasushi yoko yoshiko yoshiro yu yuka yuki
yukiko yumi yumiko yusuke yuta yuto yuu
bao bo chang chao chen cheng chun dan fang fei feng gang guang hai hao hong hua huan hui
jia jian jiang jie jin jing jun kai lan lei li lian liang lin ling mei min ming na ning
peng ping qian qiang qing qiu rong rui shan shu tao ting wei wen xia xiang xiao xin xiu
xue yan yang yi ying yong yu yuan yun zhen zhi zhong zhou
ae-ri bo-ra chan-wook da-eun do-yun eun-ji eun-young ha-eun hye-jin hyun-woo ji-ho
ji-hoon ji-min ji-woo ji-yeon jin-ho joon-ho jung-hoon kyung-soo min-ho min-ji min-jun
seo-yeon seo-yun soo-jin sung-min woo-jin ye-jin yeon-woo young-ho yu-na
anh binh chau cuong dung duc giang ha hanh hieu hoa hoang hung huong huy khanh lan
linh long mai minh my nam ngoc nguyet nhung phuong quang quynh son tam thanh thao thi
thu thuy tien trang tri trung tuan tuyet van viet vinh
arief bambang budi dewi eko fitri hendra indah joko kartika putri rina sari siti
sri wahyu yanti agus andi bayu dian gilang intan rizky
aiyana kalani keanu leilani makoa malia noelani
abbie ace adalyn addie aden adonis aisling alayna alden alfonzo alivia allie alyson amari
amaya ambrose amos anderson angus annalise annika ansel archer ari aria arlo asher aspen
atticus aubree august aurelia avianna axel bailey baxter beau beckett bennett bentley
bethan blair bodhi bonita booker bowen braden braxton brayden brenna briar bridgette
britney brock bronson brynn cade cadence caitlin callie camden camille carina carmela
carson cason cecily chanel chase cheyenne cierra clark clementine colton conrad cooper
cortez dakota dallas damien dana daria davina dawson delaney delilah demetrius denver
destiny dominick donnie dorian dudley easton eden edwina eldon elian ellis elmer elvin
elvis emery emmeline enid ernie esmeralda estella ethan everly ezekiel fallon finley
finn fletcher frida gage galen garrison gavin genesis gianna gina gloria graydon greer
gunner gus hadley harlan harper hattie hollis hope huxley ingram isadora ivory jace
jaden jaelyn jalen jamal jameson janae jarvis jaxon jaylen jensen jett joaquin jodie
jolene judson kadence kaiden kaleb kamryn kane kasey keegan kellan kelvin kendrick
kennedy kenzie khalil kiara kieran kingston kinsley kira kobe kristopher lachlan laila
landry larkin latoya lauryn layne lennon lenore leona lettie lexie lila linus lionel
lorenzo lottie lowell luann lucian luna lyla macy maddox maeve makayla malachi marcel
margot marley marlon matilda mckenzie mekhi micaela milo mirabel moira monty myles
nadine nash nevaeh niall nico nolan nyla odette odin orion orson otto paisley parker
paxton penelope phineas porter presley quinton raelynn ramona reagan reese remy rhett
rhys ricky river roman rosalind rosie rowena royce ryder sabrina saige salome sawyer
scarlet selah serena shelton sierra silvia sloane soren stefan sutton tatum tegan
teagan thatcher theresa thea tobias trey tucker tyson valentina vaughan vivienne
waylon weston wilder willow winona wren wynn yara zander zaria zion
aadhya aaradhya abhinaya abirami akila alagu amudha anbu annamalai aravind arulmozhi
bala balamurugan bhaskar chinnaswamy deepan dhanush ezhil ganesan gokul gowri harini
ilango indu janaki jeyaraj kalaivani kalyani kannan karthika kathir kumaran lavanya
madhavan malathi mani manikandan meenakshi murugan muthu nagaraj nandhini nirmal
padma palani parvathi ponni prabhakar priyadarshini rajkumar ramya ranjani revathi
sangita saranya saravanan selvam selvi senthil shanthi sivakumar sowmya subramanian
sundar surya tamilselvan thamarai thilak uthra vaishnavi valli velu venkatesh vignesh
anirban arindam debashish indranil joydeep partha prosenjit rituparna sabyasachi
souvik subhajit sudipta tanmoy amritpal baljit gurpreet harjit harpreet inderjit
jaspreet kuldeep manpreet navjot parminder rajinder sukhwinder tejinder
alex ana ana-maria elena-maria hiro jean-pierre kumar liu louis-philippe maya wang zhang
"""

# Also ordinary English words, months or places: they type multi-word names only.
AMBIGUOUS = """
april art august autumn bill bo brook brooke chase chad christian dallas dawn dean drew
faith fern florence frank georgia ginger grace grant hazel heath holly hope hunter iris ivy
jade jordan joy june ken kim lane lee lincoln long mark max may me melody miles min mo
nam page pat pearl penny rich rob robin rose ruby sage sandy song sky son star stella
sterling summer tam tao van victoria violet will win wolf yu ai an sun hope phoenix sydney
austin chandler paris clay reed rocky gene don ray guy hal ned bo dan jan ha na ling
lan tam thanh my long mai li yi hui xin kai rin ren sora una piper skylar madison
savannah trinity harmony mercy patience precious unity willow river aurora
wren aspen sage autumn haven honor journey kingston legend lyric
"""
