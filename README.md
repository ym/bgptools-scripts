# bgptools-scripts

This repository contains a collection of scripts that can be used to send MAC addresses to [bgp.tools](https://bgp.tools) from your own [LibreNMS](https://www.librenms.org/) deployment.

## Usage

Please clone the repository and run the scripts from the cloned directory.
Python >= 3.9 and poetry are required.

For the scripts to work, you need to set the following environment variables:

* `LIBRENMS_TOKEN`: The API token for your LibreNMS deployment
* `LIBRENMS_URL`: The URL to your LibreNMS deployment
* `BGPTOOLS_ENDPOINT`: The URL to BGP.tools internal API endpoint

If you haven't created an API token yet, you find instructions on how to do so [here](https://docs.librenms.org/API/#tokens).

```bash
git clone https://github.com/ym/bgptools-scripts.git
cd bgptools-scripts
poetry install --no-dev
LIBRENMS_URL=https://librenms.example.com/ \
LIBRENMS_TOKEN=1234567890 \
BGPTOOLS_ENDPOINT=https://bgptools.example.com/ \
poetry run ./ixpmac.py YOUR_ASN_1 YOUR_ASN_2
```

### With Docker

```bash
docker run \
-e LIBRENMS_URL=https://librenms.example.com/ \
-e LIBRENMS_TOKEN=1234567890 \
-e BGPTOOLS_ENDPOINT=https://bgptools.example.com/ \
aveline/bgptools-ixpmac YOUR_ASN_1 YOUR_ASN_2
```
