DNS_DIRECT_SERVER = "223.5.5.5"
DNS_REMOTE_SERVER = "1.1.1.1"
DNS_REMOTE_PATH = "/dns-query"
GEOIP_CN_RULESET_URL = "https://fastly.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs"

SKIP_PROXY_DOMAINS = ["localhost", "captive.apple.com"]
SKIP_PROXY_SUFFIXES = ["local"]
DNS_DIRECT_ONLY_DOMAINS = ["cp.cloudflare.com"]
DNS_DIRECT_ONLY_SUFFIXES = ["in-addr.arpa", "ip6.arpa"]
TUN_EXCLUDED_ROUTES = [
    "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24",
    "192.168.0.0/16", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "255.255.255.255/32", "239.255.255.250/32",
]

DIRECT_EXACT = [
    "blzddist1-a.akamaihd.net", "download.jetbrains.com", "file-igamecj.akamaized.net", "images-cn.ssl-images-amazon.com", "officecdn-microsoft-com.akamaized.net", "speedtest.macpaw.com", "www-cdn.icloud.com.akadns.net",
]

PROXY_EXACT = [
    "copilot.microsoft.com", "copilot.bing.com", "cdn.angruo.com", "api.statsig.com", "browser-intake-datadoghq.com", "chat.openai.com.cdn.cloudflare.net", "o33249.ingest.sentry.io", "openai-api.arkoselabs.com", "openaicom-api-bdcpf8c6d2e9atf6.z01.azurefd.net", "openaicomproductionae4b.blob.core.windows.net", "production-openaicom-storage.azureedge.net", "static.cloudflareinsights.com",
]

DIRECT_SUFFIX = [
    "baidu.com", "baidubcr.com", "bdstatic.com", "yunjiasu-cdn.net", "taobao.com", "alicdn.com", "126.net", "127.net", "163.com", "163yun.com", "21cn.com", "343480.com", "360buyimg.com", "360in.com", "51ym.me", "71.am.com",
    "8686c.com", "abchina.com", "accuweather.com", "acgvideo.com", "acm.org", "acs.org", "aicoinstorge.com", "aip.org", "air-matters.com", "air-matters.io", "aixifan.com", "akadns.net", "alibaba.com", "alikunlun.com", "alipay.com", "amap.com",
    "amd.com", "ams.org", "animebytes.tv", "annualreviews.org", "aps.org", "ascelibrary.org", "asm.org", "asme.org", "astm.org", "autonavi.com", "awesome-hd.me", "b612.net", "baduziyuan.com", "bdatu.com", "beitaichufang.com", "biliapi.com",
    "biliapi.net", "bilibili.com", "bilibili.tv", "bjango.com", "bmj.com", "booking.com", "broadcasthe.net", "bstatic.com", "cailianpress.com", "cambridge.org", "camera360.com", "cas.org", "ccgslb.com", "ccgslb.net", "cctv.com", "cctvpic.com",
    "chdbits.co", "chinanetcenter.com", "chinaso.com", "chua.pro", "chuimg.com", "chunyu.mobi", "chushou.tv", "clarivate.com", "classix-unlimited.co.uk", "cmbchina.com", "cmbimg.com", "cn", "com-hs-hkdy.com", "ctrip.com", "czybjz.com", "dandanzan.com",
    "dfcfw.com", "didialift.com", "didiglobal.com", "dingtalk.com", "docschina.org", "douban.com", "doubanio.com", "douyu.com", "duokan.com", "dxycdn.com", "dytt8.net", "eastmoney.com", "ebscohost.com", "emerald.com", "empornium.me", "engineeringvillage.com",
    "eudic.net", "feiliao.com", "feng.com", "fengkongcloud.com", "fjhps.com", "frdic.com", "futu5.com", "futunn.com", "gandi.net", "gazellegames.net", "geilicdn.com", "gifshow.com", "godic.net", "gtimg.com", "hdbits.org", "hdchina.org",
    "hdhome.org", "hdsky.me", "hdslb.com", "hicloud.com", "hitv.com", "hongxiu.com", "hostbuf.com", "huxiucdn.com", "huya.com", "icetorrent.org", "icevirtuallibrary.com", "iciba.com", "idqqimg.com", "ieee.org", "iesdouyin.com", "igamecj.com",
    "imf.org", "infinitynewtab.com", "iop.org", "ip-cdn.com", "ip.la", "ipip.net", "ipv6-test.com", "iqiyi.com", "iqiyipic.com", "ithome.com", "jamanetwork.com", "java.com", "jd.com", "jd.hk", "jdpay.com", "jhu.edu",
    "jidian.im", "jpopsuki.eu", "jstor.org", "jstucdn.com", "kaiyanapp.com", "karger.com", "kaspersky-labs.com", "keepcdn.com", "keepfrds.com", "kkmh.com", "ksosoft.com", "kuyunbo.club", "libguides.com", "livechina.com", "lofter.com", "loli.net",
    "luojilab.com", "madsrevolution.net", "maoyan.com", "maoyun.tv", "meipai.com", "meitu.com", "meituan.com", "meituan.net", "meitudata.com", "meitustat.com", "meixincdn.com", "mgtv.com", "mi-img.com", "microsoft.com", "miui.com", "miwifi.com",
    "mobike.com", "moke.com", "morethan.tv", "mpg.de", "msecnd.net", "mubu.com", "mxhichina.com", "myanonamouse.net", "myapp.com", "myilibrary.com", "myqcloud.com", "myzaker.com", "nanyangpt.com", "nature.com", "ncore.cc", "netease.com",
    "netspeedtestmaster.com", "nim-lang-cn.org", "nvidia.com", "oecd-ilibrary.org", "office365.com", "open.cd", "oracle.com", "osapublishing.org", "oup.com", "ourbits.club", "ourdvs.com", "outlook.com", "ovid.com", "oxfordartonline.com", "oxfordbibliographies.com", "oxfordmusiconline.com",
    "passthepopcorn.me", "paypal.com", "paypalobjects.com", "pnas.org", "privatehd.to", "proquest.com", "pstatp.com", "pterclub.com", "qdaily.com", "qhimg.com", "qhres.com", "qidian.com", "qq.com", "dns.pub", "doh.pub",
    "qyer.com", "qyerstatic.com", "raychase.net", "redacted.ch", "ronghub.com", "rsc.org", "ruguoapp.com", "s-microsoft.com", "s-reader.com", "sagepub.com", "sankuai.com", "sciencedirect.com", "scomper.me", "scopus.com", "seafile.com", "servicewechat.com",
    "siam.org", "sina.com", "sm.ms", "smzdm.com", "snapdrop.net", "snssdk.com", "snwx.com", "sogo.com", "sogou.com", "sogoucdn.com", "sohu-inc.com", "sohu.com", "sohucs.com", "soku.com", "spiedigitallibrary.org", "springer.com",
    "springerlink.com", "springsunday.net", "sspai.com", "staticdn.net", "steam-chat.com", "steamcdn-a.akamaihd.net", "steamcontent.com", "steamgames.com", "steampowered.com", "steamstat.us", "steamstatic.com", "steamusercontent.com", "takungpao.com", "tandfonline.com", "tencent-cloud.net", "tencent.com",
    "tenpay.com", "test-ipv6.com", "tianyancha.com", "tjupt.org", "tmall.com", "tmall.hk", "totheglory.im", "toutiao.com", "udache.com", "udacity.com", "un.org", "uni-bielefeld.de", "uning.com", "v-56.com", "visualstudio.com", "vmware.com",
    "wangsu.com", "weather.com", "webofknowledge.com", "wechat.com", "weibo.com", "weibocdn.com", "weico.cc", "weidian.com", "westlaw.com", "whatismyip.com", "wiley.com", "windows.com", "windowsupdate.com", "worldbank.org", "worldscientific.com", "xiachufang.com",
    "xiami.com", "xiami.net", "xiaomi.com", "xiaohongshu.com", "xhscdn.com", "ximalaya.com", "xinhuanet.com", "xmcdn.com", "yangkeduo.com", "ydstatic.com", "youku.com", "zhangzishi.cc", "zhihu.com", "zhimg.com", "zhuihd.com", "zimuzu.io",
    "zimuzu.tv", "zmz2019.com", "zmzapi.com", "zmzapi.net", "zmzfile.com", "manmanbuy.com", "aaplimg.com", "apple-cloudkit.com", "apple.co", "apple.com", "apple.news", "apple.com.cn", "appstore.com", "cdn-apple.com", "crashlytics.com", "icloud-content.com",
    "icloud.com", "icloud.com.cn", "me.com", "mzstatic.com", "ykimg.com",
]

PROXY_SUFFIX = [
    "apple-relay.akamaized.net", "apple-relay.apple.com", "apple-relay.cloudflare.com", "apple-relay.fastly-edge.com", "apple-relay.mask.apple-dns.net", "battle.net", "blizzard.com", "getpricetag.com", "m-team.cc", "sciencemag.org", "teamviewer.com", "v2ex.com", "scdn.co", "line.naver.jp", "line.me", "line-apps.com",
    "line-cdn.net", "line-scdn.net", "abc.xyz", "goog", "admin.recaptcha.net", "ampproject.org", "android.com", "androidify.com", "appspot.com", "autodraw.com", "blogger.com", "capitalg.com", "certificate-transparency.org", "chrome.com", "chromeexperiments.com", "chromestatus.com",
    "chromium.org", "creativelab5.com", "debug.com", "deepmind.com", "dialogflow.com", "firebaseio.com", "getmdl.io", "getoutline.org", "ggpht.com", "gmail.com", "gmodules.com", "godoc.org", "golang.org", "gstatic.com", "gv.com", "gvt0.com",
    "gvt1.com", "gvt3.com", "gwtproject.org", "itasoftware.com", "madewithcode.com", "material.io", "polymer-project.org", "recaptcha.net", "shattered.io", "synergyse.com", "telephony.goog", "tensorflow.org", "tfhub.dev", "tiltbrush.com", "waveprotocol.org", "waymo.com",
    "webmproject.org", "webrtc.org", "whatbrowser.org", "widevine.com", "x.company", "xn--ngstr-lra8j.com", "youtu.be", "yt.be", "ytimg.com", "clubhouseapi.com", "clubhouse.pubnub.com", "joinclubhouse.com", "ap3.agora.io", "instagram.com", "cdninstagram.com", "instagr.am",
    "fb.com", "meta.com", "twimg.com", "x.com", "t.co", "kenengba.com", "akamai.net", "whatsapp.net", "whatsapp.com", "snapchat.com", "amazonaws.com", "angularjs.org", "akamaihd.net", "amazon.com", "bit.ly", "bitbucket.org",
    "blog.com", "blogcdn.com", "blogsmithmedia.com", "box.net", "bloomberg.com", "cl.ly", "cloudfront.net", "cloudflare.com", "cocoapods.org", "dribbble.com", "dropbox.com", "dropboxstatic.com", "dropboxusercontent.com", "docker.com", "duckduckgo.com", "digicert.com",
    "dnsimple.com", "edgecastcdn.net", "engadget.com", "eurekavpt.com", "fb.me", "fbcdn.net", "fc2.com", "feedburner.com", "fabric.io", "flickr.com", "fastly.net", "github.com", "github.io", "githubusercontent.com", "goo.gl", "godaddy.com",
    "gravatar.com", "imageshack.us", "imgur.com", "jshint.com", "ift.tt", "j.mp", "kat.cr", "linode.com", "lithium.com", "megaupload.com", "mobile01.com", "modmyi.com", "nytimes.com", "name.com", "openvpn.net", "openwrt.org",
    "ow.ly", "pinboard.in", "ssl-images-amazon.com", "sstatic.net", "stackoverflow.com", "staticflickr.com", "squarespace.com", "symcd.com", "symcb.com", "symauth.com", "ubnt.com", "thepiratebay.org", "tumblr.com", "twitch.tv", "twitter.com", "wikipedia.com",
    "wikipedia.org", "wikimedia.org", "wordpress.com", "wsj.com", "wsj.net", "wp.com", "vimeo.com", "tapbots.com", "medium.com", "fast.com", "nflxvideo.net", "linkedin.com", "licdn.com", "bing.com", "zoom.us", "soundcloud.com",
    "sndcdn.com", "algolia.net", "auth0.com", "cdn.cloudflare.net", "challenges.cloudflare.com", "chatgpt.livekit.cloud", "client-api.arkoselabs.com", "events.statsigapi.net", "featuregates.org", "host.livekit.cloud", "identrust.com", "intercom.io", "intercomcdn.com", "launchdarkly.com", "oaistatic.com", "oaiusercontent.com",
    "observeit.net", "openai.com", "openaiapi-site.azureedge.net", "openaicom.imgix.net", "poe.com", "segment.io", "sentry.io", "stripe.com", "turn.livekit.cloud", "t.me", "tdesktop.com", "telegra.ph", "telegram.me", "telegram.org", "telesco.pe", "dnsleaktest.com",
    "dnsleak.com", "expressvpn.com", "nordvpn.com", "surfshark.com", "ipleak.net", "perfect-privacy.com", "browserleaks.com", "browserleaks.org", "vpnunlimited.com", "whoer.net", "whrq.net",
]

DIRECT_KEYWORD = []

PROXY_KEYWORD = [
    "blogspot", "google", "aka", "facebook", "youtube", "twitter", "instagram", "gmail", "pixiv", "openaicom-api",
]

DIRECT_CIDR = [
    "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "127.0.0.0/8",
]

PROXY_CIDR = [
    "24.199.123.28/32", "45.76.214.191/32", "64.23.132.171/32", "143.198.200.27/32", "159.89.204.203/32", "91.108.4.0/22", "91.108.8.0/22", "91.108.12.0/22", "91.108.16.0/22", "91.108.56.0/22", "109.239.140.0/24", "149.154.160.0/20", "2001:B28:F23D::/48", "2001:B28:F23F::/48", "2001:67C:4E8::/48",
]

IGNORED_RULES = [
    "IP-ASN,132203,DIRECT,no-resolve", "USER-AGENT,Line*,PROXY",
]

ROUTE_FINAL = "route-mode"
USE_GEOIP_CN = True


def _merge_unique(*groups):
    merged = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged


def build_dns_config(hosts):
    """
    1.12.0+ 迁移重点：
    - 为拨号 DNS (如 DoH) 显式指定 domain_resolver
    """
    if not hosts:
        raise ValueError("hosts is required")

    rules = [
        {
            "domain": [hosts["reality"], hosts["tuic"], hosts["hy2"]],
            "server": "dns-direct",
        }
    ]

    direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, DNS_DIRECT_ONLY_DOMAINS, DIRECT_EXACT)
    direct_suffix = _merge_unique(SKIP_PROXY_SUFFIXES, DNS_DIRECT_ONLY_SUFFIXES, DIRECT_SUFFIX)

    if direct_exact:
        rules.append({"domain": direct_exact, "server": "dns-direct"})
    if PROXY_EXACT:
        rules.append({"domain": PROXY_EXACT, "server": "dns-remote"})
    if direct_suffix:
        rules.append({"domain_suffix": direct_suffix, "server": "dns-direct"})
    if PROXY_SUFFIX:
        rules.append({"domain_suffix": PROXY_SUFFIX, "server": "dns-remote"})
    if DIRECT_KEYWORD:
        rules.append({"domain_keyword": DIRECT_KEYWORD, "server": "dns-direct"})
    if PROXY_KEYWORD:
        rules.append({"domain_keyword": PROXY_KEYWORD, "server": "dns-remote"})

    return {
        "servers": [
            {
                "type": "udp",
                "tag": "dns-direct",
                "server": DNS_DIRECT_SERVER,
            },
            {
                "type": "https",
                "tag": "dns-remote",
                "server": DNS_REMOTE_SERVER,
                "path": DNS_REMOTE_PATH,
                "detour": "global",
                "domain_resolver": "dns-direct",
            },
        ],
        "rules": rules,
        "final": "dns-remote",
        "strategy": "prefer_ipv4",
    }


def build_route_config(sniff_inbound=None):
    """
    1.12.0+ 迁移重点：
    - 增加 default_domain_resolver
    """
    rules = [
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_is_private": True, "action": "route", "outbound": "direct"},
    ]

    if sniff_inbound:
        rules.insert(0, {"inbound": sniff_inbound, "action": "sniff", "timeout": "1s"})
        rules.insert(0, {"inbound": sniff_inbound, "action": "resolve", "strategy": "prefer_ipv4"})

    direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, DIRECT_EXACT)
    direct_suffix = _merge_unique(SKIP_PROXY_SUFFIXES, DIRECT_SUFFIX)

    if direct_exact:
        rules.append({"domain": direct_exact, "action": "route", "outbound": "direct"})
    if PROXY_EXACT:
        rules.append({"domain": PROXY_EXACT, "action": "route", "outbound": "global"})
    if direct_suffix:
        rules.append({"domain_suffix": direct_suffix, "action": "route", "outbound": "direct"})
    if PROXY_SUFFIX:
        rules.append({"domain_suffix": PROXY_SUFFIX, "action": "route", "outbound": "global"})
    if DIRECT_KEYWORD:
        rules.append({"domain_keyword": DIRECT_KEYWORD, "action": "route", "outbound": "direct"})
    if PROXY_KEYWORD:
        rules.append({"domain_keyword": PROXY_KEYWORD, "action": "route", "outbound": "global"})
    if DIRECT_CIDR:
        rules.append({"ip_cidr": DIRECT_CIDR, "action": "route", "outbound": "direct"})
    if PROXY_CIDR:
        rules.append({"ip_cidr": PROXY_CIDR, "action": "route", "outbound": "global"})

    route = {
        "rules": rules,
        "final": ROUTE_FINAL,
        "auto_detect_interface": True,
        "default_domain_resolver": "dns-direct",
    }

    if USE_GEOIP_CN:
        route["rule_set"] = [
            {
                "type": "remote",
                "tag": "geoip-cn",
                "format": "binary",
                "url": GEOIP_CN_RULESET_URL,
                "download_detour": "direct",
            }
        ]
        route["rules"].append(
            {
                "rule_set": "geoip-cn",
                "action": "route",
                "outbound": "direct",
            }
        )

    return route
