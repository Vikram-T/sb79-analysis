# Agenda
1. Motivation
2. How we Built it Step By Step
3. Net Capacity Calculations
4. Results
5. Next Steps/Help Needed

# Why did we build this?
1. How much capacity does SB-79 add?
   * If cities want to come up with their own plan they would need to match the capacity that SB-79 upzones for
   * Image showing local plan capacity = SB-79 Capacity
   * This would help cities know if they are in compliance or not
# How we built it
## Calculate existing capacity
1. To calculate capacity we needed to know
    1. What parcels were upzoned?
## Step 1: City Boundary
* For this we are using Berkeley as our first example
(image)

## Step 2:
* After getting the city boundary we go ahead and map the tier1 and tier2 transit stops 
* Berkeley only has these tier1 stops
(Image)

## Step 3: Zone Rings
* Next we calculate which parcels would be upzoned
* (Image)
* Chart for 200ft to quarter mile to half mile 

## Step 4a: Calculating Capacity Increase
* After this it should be pretty simple to calculate capacity right? We just need to add the upzoned capacity together?
* Not quite, there is a clause in zone capacity calculations that incentivizes development on undeveloped land

## Step 4b: Calculating Capacity Increase cont
* Here we see 2 identical parcels of 1 acre,
* One with a parking lot and another with 100 existing units
* SB-79 says that this zone adds 60 while this one adds 160
* (show calculation)
* Show images of the lots 
(I think I want an image of a person looking from the street the idea would be that we see an apartment next to one of a parking lot from first person POV and the calculations are shown below or above each)

# Results
* Using all this information we can get a baseline of what SB-79 adds
* Show results for berkeley

# Next Steps
## Adding existing zoning capacity
    -> This is complicated because while Berkeley has a maximum dua for some zones 
    -> For others we need to calculate it based on FAR + and this explanation:
    A lot of Berkeley has maximum density standards. I know it's 70 dua for the middle housing zones (R-1, R-2, R-2A, MUR); the max FAR in those zones is functionally 1.8 (35 ft = 3 stories, 60% max lot coverage). The higher R & C zones do seem to be fully form based; best way to estimate allowed FAR there is height (in stories) * lot coverage (as a decimal) 
## Expanding to Other cities
* We would love to be able to expand to other cities but need help from people who 
    -> Can help set up the functions around their city's API
    -> Know the rules around calculating exisiting capacity
## Thank you
* See the demo live here: https://vikram-t.github.io/sb79-analysis/public/
* Code: https://github.com/Vikram-T/sb79-analysis/
* This Presentation: vikram-t.github.io/sb79-analysis/presentation

