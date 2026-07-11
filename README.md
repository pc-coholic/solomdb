SoloMDB
=======
Use a SumUp Solo card payment terminal as an MDB Cashless Device on your 
vending machine.

Disclaimer
----------
This project is neither endorsed nor supported by SumUp, its affiliates. Using 
a SumUp device like this might or might not be violating SumUp's and/or the 
payment networks' TOS. 

SumUp devices do not fulfil the requirements for unattended payment devices set
out by the Payment Card Industry Security Standards Council.

This code comes with absolutely no warranties - explicit or implied. Use at your 
own risk.

Requirements
------------
- SumUp Solo (Solo, not Solo Lite, Air, Terminal or other)
- SumUp merchant account
- SumUp API key
- SumUp Affiliate key
- MDB-Interface
  - Either from [Qiba/Qibixx](https://www.shop.qiba.pt/en/shop)
  - Or from [Waferstar/Waferlife](http://www.waferstar.com/en/index.html)

You can sign up for a SumUp merchant account directly on their webpage - you 
may also use this [referral link](https://join.sumup.com/c-G57-5X?share_id=tfjfyxJc-g57-5x) 
to show your appreciation for this project and give a donation to the [CCC Munich](https://muc.ccc.de/).

SumUp Solo payment terminals are available for purchase during signup and at 
from within the merchant dashboard. Some local big box electronics chains do also 
carry SumUp terminals for purchase.

Please be aware that this project only works with SumUp Solo devices. Neither similar 
named devices (like the Solo Lite) or other devices will work.

> **_NOTE:_**  Technically speaking, any stand-alone (WiFi/WWAN) capable device will 
> work, as long as it supports [SumUp's Cloud API](https://developer.sumup.com/terminal-payments/cloud-api).

The SumUp API-key as well as the Affiliate key can be obtained from the [SumUp 
Developer Dashboard](https://me.sumup.com/settings/developer). The Affiliate 
Key serves to identify your application; it is not a referral token to earn 
commissions for advertising SumUp's services to prospective new merchants.

This project supports only two manufacturers of MDB devices at this point: Qiba/Qibixx and 
Waferstar/Waferlife. The former provides high quality devices that offer advanced
features like MITM/MDB traffic analysis-features, the possibility to use the interface
as well as a MDB-Slave or -Master and provides shorthand/comfort functions for some 
predefined use cases like "pretend to be a cashless device" or "pretend to be a VMC" without 
the need to do all the complicated state-handling yourself and excellent customer service. 

All this comfort does however come with a slightly higher price tag.

You can choose between the DIN-Rail modules or Raspberry Pi hats. Just make sure to pick a 
variant that does indeed provide Slave/Peripherial functions. Having "VMC" in its name is 
generally a sign that you're looking at the wrong product!

On the other hand of the spectrum you find the devices offered by Waferstar/Waferlife. Their 
primary sales channels are through their AliExpress shop and sometimes Amazon and eBay.

Generally speaking, they are offering two product lines in two form factors: RS232-MDB and
MDB-RS232; both available as USB/Serial interfaces and as a RaspberryPi hat.

> **_NOTE:_** Make sure to get the **RS232-MDB**, as this interface allows you to implement 
> a cashless device on the MDB-bus, connecting to an existing VMC.
> 
> The MDB-RS232 is the wrong product - you would be using this if you wanted to implement a 
> VMC and connect other peripherals (like coin and bill acceptors) to your computer.

> **_NOTE:_** Double and triple check when ordering. Especially with the RPi hat the item 
> description and pictures tend to not always line up. The PCB should feature a red dip-switch
> block and a single transparent-white MDB connector.
> 
> If the hat lacks the DIP-switches and has a green, two-pin power receptacle next to the MDB-port,
> you are looking at the wrong, MDB-RS232, hat.

Host Setup
----------
Create a new `solomdb.ini` config file (or duplicate the existing `solomdb.ini.dist`) and 
provide the required values. Make sure to set the `devicetype` to either `qibixx` or 
`waferstar` - depending on the MDB interface you are using.

For the first launch (or whenever changing the SumUp device), you'll need to pair the reader.

To do so, power up the SumUp device, and connect to WiFi or WWAN.

> **_NOTE:_** While not required for operation of SoloMDB, it is recommended to connect to 
> WiFi, log into the device using the merchant credentials and to **install any available updates**.
> 
> Once the newest updates are installed, feel free to log out again.

Once connected to the network, swipe down from the top, select `Connections` and then `API`.

Start the pairing process on the device and run 
`python solomdb.py --pair-reader <pairing code> --name <device name>`. You can use any name to 
identify your reader later on.

> **_NOTE:_** Once pairing has completed successfully, you can "lock" the reader by swiping 
> from the top, selecting `Settings`, `Security lock` and following the instructions.
> 
> This lock does not really deserve the name of a proper lock - it is merely a slight deterrent 
> to the casual explorer.
> 
> This is also why SumUp terminals should never be left unattended. 

You can now run the service with `python solomdb.py`.

VMC Setup
---------
We assume a Level 3 VMC and also pretend to be a Level 3 cashless device, supporting 
`Always Idle`. You might want to configure your VMC accordingly.

You might also want to set the timeout for the cashless vending session to at least 60 seconds; 
120 are recommended, as this represents SumUp's timeout for an abandoned payment.

Advanced usage
--------------
If your VMC does not support `Always idle` and needs the cashless device to start the cashless 
session, you can do so by `POST`ing to `/start` on the device soloMDB is running.

By default, the server will be listening on all interfaces on port `8000`, you may however 
override these settings by passing the optional `--host` and `--port` parameters.

You could then set up a small daemon listening to a GPIO button press to send the request. Or 
set up a button connected to your [Home Assistant](https://www.home-assistant.io/). Or perhaps 
you'd prefer a solution with [ESPHome](https://esphome.io/)? The sky is the limit!

solomdb.ini config options
--------------------------
- `devicetype` (required): either `qibixx` or `waferstar`, depending on your MDB interface
- `mdbdevice` (required): path like `/dev/ttyUSB0` to the MDB interface
- `apikey` (required): SumUp API-key starting wit `sup_sk_`
- `affiliate_app_id` (required): SumUp Affiliate Application ID
- `affiliate_key` (required): SumUp Affiliate Key
- `sale_description` (optional): Descriptor of the transaction shown in SumUp backend and receipt. Defaults to `SoloMDB`
- `min_sale_amount` (optional): Minimum sale amount supported by SumUp/the terminal. Defaults to 1.00 Euro

Known working environments
--------------------------
- Sielaff FS1500 with Qibixx interface at [Temporärhaus](https://wiki.temporaerhaus.de/spiralautomat/sielaff-fs-1500)
- Sielaff SiLine GF L with Waferstar RPi hat at [CCC München](https://wiki.muc.ccc.de/matemat:robimat:start)