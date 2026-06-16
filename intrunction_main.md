Build me a software app that groups IP adresses to subnets.

Goal:
- Group Ip addresses with a subnet mask as big as possible, so that the subnet has as little host slots as possible.

Input:
- txt file which contains IP adresses separated by Enter

Output:
- txt file which contains IP subnets and corespondent input IP adresses that are associated with it

Steps:
1. group IPs by MSB byte
2. for each group:
    2.1. transform next byte from decimal to binary
    2.2 see which are the addresses with most MSBs similar and group them
    2.3 continue with the next most MSBs similar and group until you have no nore bits, or there's no way to group the remaining IPs
3. the remaining IPs will be /32

Requirements:
- groups must have the mask between /8 and /24
- erase the previous lines from the output file before adding the current lines