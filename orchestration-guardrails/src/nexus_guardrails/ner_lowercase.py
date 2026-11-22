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

"""Words that must not be read as names or places in all-lowercase text (data only).

Given names and places that are also English words ("will", "grace", "nice", "reading"):
in lowercase chat a lexicon hit is taken as a name or place only when it is not one of these.
"""

from __future__ import annotations

# Names and places that are also ordinary words.
STOP = """
aba abbas abigail aby acapulco ace acre acropolis adit admiralty agar agen ahsan ai aisling akin
alan alannah alba alec alfonso alin alison allan ally alma along alpine ama amala amani amapa
amarillo amber ambrose amelia amine amir amy an ana anam anan anchorage anele angel angelica anis
ann ansar antarctica ante antipolo araba arad arati archer arctic aria ariel arles arrah arras art
arusha ashraf asok aspen astrakhan atlantic atta august aurelia aurora autumn ava ayu babu babul
baby baga bago bahar bailey baku balaghat bali bally banda bandstand bar barbel bari baris barrow
barry bas bath batman baxter beata beau begum beira bela ben bender benedict benjamin bennet benny
berne bertram beth bhakti bibi bidar bill billy binal bing binh blair blake blanca blas bo bob
bobby bobo bode bodhi bogum bolivia bong booker bora bose boulder brad brandy bray bree brent brett
briar broadway brock brook brunswick bubby buffalo bund bunty burbank bursa burton bury cade
cadence calais camilla camp can candela canton capucine carina carl carmine carol caroline carter
catalina cayenne celeste centennial central centurion chad chai chalon champagne champaign chandam
chandler chandu chang chao charity chase cheng cherry chester chi chico chinky chitra chowk chun
clark clay clemence clement clint clive cole colima colin colleen colmar colorado concord cooper
cora cordoba corinne cork corona cortez cortina crawley croydon crystal curacao cyrus da dag daisy
dale daler dali dalton daman dan dang darshana daud davenport dawn dayal deal dean dearborn deb dee
deep dele delft delphine derby derrick derry desi destiny dev deva dexter dhan dhanush dharani dian
dick dieter dilli dimple dirk dola dolly don dong donna dorje dover drew dudley dung dunstable earl
eastern ebony edit elaine emery emma eric erika esplanade ethel etna eve faith fakir fang faro
fatiha fay fei felicity fern fez fife filippo finland flagstaff flatiron fletcher flint flora
florence florin flushing fort francisca franco frank franklin frederik free fresno fu fuji fulham
gabi gad gage gambia gang ganga ganja gap garland garrison gayatri gemma gene genesis genet gent
geo gilbert ginger glen goldy gora goran gosport grace graham granada grant griffin guernsey gugu
guinea gul gulf guna gunner gunter guru guy ha hackney hafiz hail hakim hala hamlet hammersmith
hanif hank hanna hao happy harm harman harmony harper harrow harsh hastings havelock haven hayward
hazel heath heather hector heer hemal herne hidalgo hind hiro holly hong honor hop hope horst hove
hue hull hung hyacinth iceland ife imperia independence inwood ion irene iris iva ivory ivy jack
jacobus jade jagat jake jama jami jane jasmine jasper jay jean jeff jenna jerez jerry jersey jihad
jimmy jing jinja jo joe joey johannes joke jolly jordan josh josie journey joy juba jugal julio
june juniper kai kaiser kala kamala kana karma karwar kay keita kelly kelvin ken kensington kent
kerry khar kiel kiki killeen kim kirk kish kitchener knut koel konstantin koto kremlin kusum kyle
lafayette lakeland lam lama lan lance lane lansdowne larry lata laura lavish layne lazar lea league
lech lee legend lei lekha lemma lev levant lewis li liang liege lien lier lily liming lin lina line
ling linn lino lionel loan lochan lone long lora lori loris love lovely lucerne lucky luke luna
lupe ly lyra lyric macao madeline mae maha mahua maidenhead maire majestic maki malate malati male
mali malik mana manal manas mangal mangi mango mani manly mantua mao mapo maral marc marcel
marcello marco margarita marguerite marigold marikina marina marine mark mashal mason massa matara
mate matti maxim maxwell may maya me mediterranean meet melody meng mercy merel meridian merlin
mesa mesopotamia mesquite michigan midland midway mike mila milo min mina ming minnie mirza misty
mitra mo mobile modena molly mon mona monas montana morgan morocco morris moss most mou mozambique
mu mungo munshi muse my myrtle na naa nadir naif nam nan nana nandi nandu napa nash natal nawab
nazim nazir neal nelson new newmarket newton ni nice nick nicky nicolo nizam noa noble noel norma
novena oban oceanside odd oisin olena om omer opal orange ordu otto outback pablo pacific page pal
pali palma pam panama pandora paolo papa pappi para paraiba param parel park parker parma pasan
pasang pascual pat patience patrice patty pau pavan pearl pedro peggy peine penny pentagon per
peregrine pereira perm perry pete petronella peyton phoebe phoenix pia piedmont piet pilar pimlico
ping pinky piper plantation plateau plock pontianak porter portia porto prabhu precious presidio
primrose prince providence pueblo puja quan quinton rainer rais raja ralph ram rami ran rana randy
rani rattan ravish ray reading redding reed reem reese reina reunion rex rhea rhine rich rick riley
rim rima rimpi rio ripal rishi river riverside roanoke rob robin rocky rod rodney roger roi roque
rory rosario rose rosemary rosily ross rowan roxy ruby rufus rune rupa ruse ruth ryder sabina
sabine sabino sabra sade saga sage sahib sai said saki salar sale sally salma salta samara samba
sander sandy sang sapa sari sasa saskatoon satellite sawyer scarlet seine selah seraphina serenity
serge seth shade shahin shaikh shakti shan shaul shaw shela shelly sheng sherry shi shin shine
shiny shiv sho shraddha shun sienna sierra sika sikar silesia sina sion skive sky slough smit
smriti soho sola solan soli solo soma somerset son song sophia sora sorrento south spalding sparks
spencer sphere split sri star stein stella stephane sterling steven stipe stoke stroud sucre sue
sultan sultana sumatra summer sun sundari sunder sundri sune sunny sunrise surprise surrey swaraj
taha tai taiga taj tal tala tam tamale tamara tamas tambor tamer tammy tan tania tansy tao tapas
tapasvi tara taro tarragona taupo tauranga ted telford telluride tenderloin terry thatcher therese
tien tiffany tilly timothy tine ting titi toby tolu tom tommy tone tong tonga tonk tor tore toru
traverse travis trey tri trier trine trinity tripoli trishna troy tu tuan tuba tucker tucuman tula
tulasi tulsi tung turkey twinkle tyre tyrone udo ulla unity us uster vail valence valentine van
varna varsha vasu vedika veer vera verity vesuvius vidya ville vina viola violet viral vista wade
wale wali walter wan wang wanting warren waterfront wedding wellington wels wen west western
whistler wigan wilder will willie willow willy win wing witney wolf worcester wren wyn wynn yaba
yair yam yan yang yati yaw yen yin yoga york yuan zander zeist zimbabwe
"""
