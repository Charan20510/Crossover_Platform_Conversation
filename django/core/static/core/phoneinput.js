/* Country-code picker for phone inputs (Contact form: WhatsApp / mobile).
 * Server already normalizes phone numbers (core/utils.py: normalize_phone,
 * contact_key) — this file only has to hand it "+<cc> <number>" so typing
 * spacing/format doesn't matter to the user.
 *
 * ponytail: dial-code list covers every ITU-assigned calling code (name,
 * code) but skips shared-code split-outs (e.g. NANP members beyond +1
 * itself). Add a specific entry if a user needs to pick, say, +1 Jamaica
 * distinctly from +1 USA.
 */
(function () {
  var DIAL_CODES = [
    "93 Afghanistan","355 Albania","213 Algeria","1 American Samoa","376 Andorra","244 Angola",
    "54 Argentina","374 Armenia","297 Aruba","61 Australia","43 Austria","994 Azerbaijan",
    "1 Bahamas","973 Bahrain","880 Bangladesh","1 Barbados","375 Belarus","32 Belgium","501 Belize",
    "229 Benin","975 Bhutan","591 Bolivia","387 Bosnia and Herzegovina","267 Botswana","55 Brazil",
    "673 Brunei","359 Bulgaria","226 Burkina Faso","257 Burundi","855 Cambodia","237 Cameroon",
    "1 Canada","238 Cape Verde","236 Central African Republic","235 Chad","56 Chile","86 China",
    "57 Colombia","269 Comoros","243 Congo (DRC)","242 Congo (Republic)","506 Costa Rica",
    "385 Croatia","53 Cuba","357 Cyprus","420 Czechia","45 Denmark","253 Djibouti","1 Dominican Republic",
    "593 Ecuador","20 Egypt","503 El Salvador","240 Equatorial Guinea","291 Eritrea","372 Estonia",
    "268 Eswatini","251 Ethiopia","679 Fiji","358 Finland","33 France","241 Gabon","220 Gambia",
    "995 Georgia","49 Germany","233 Ghana","30 Greece","502 Guatemala","224 Guinea","592 Guyana",
    "509 Haiti","504 Honduras","852 Hong Kong","36 Hungary","354 Iceland","91 India","62 Indonesia",
    "98 Iran","964 Iraq","353 Ireland","972 Israel","39 Italy","225 Ivory Coast","1 Jamaica",
    "81 Japan","962 Jordan","7 Kazakhstan","254 Kenya","82 South Korea","965 Kuwait","996 Kyrgyzstan",
    "856 Laos","371 Latvia","961 Lebanon","266 Lesotho","231 Liberia","218 Libya","423 Liechtenstein",
    "370 Lithuania","352 Luxembourg","853 Macau","261 Madagascar","265 Malawi","60 Malaysia",
    "960 Maldives","223 Mali","356 Malta","222 Mauritania","230 Mauritius","52 Mexico","373 Moldova",
    "377 Monaco","976 Mongolia","382 Montenegro","212 Morocco","258 Mozambique","95 Myanmar",
    "264 Namibia","977 Nepal","31 Netherlands","64 New Zealand","505 Nicaragua","227 Niger",
    "234 Nigeria","850 North Korea","389 North Macedonia","47 Norway","968 Oman","92 Pakistan",
    "507 Panama","675 Papua New Guinea","595 Paraguay","51 Peru","63 Philippines","48 Poland",
    "351 Portugal","974 Qatar","40 Romania","7 Russia","250 Rwanda","966 Saudi Arabia","221 Senegal",
    "381 Serbia","65 Singapore","421 Slovakia","386 Slovenia","252 Somalia","27 South Africa",
    "211 South Sudan","34 Spain","94 Sri Lanka","249 Sudan","597 Suriname","46 Sweden","41 Switzerland",
    "963 Syria","886 Taiwan","992 Tajikistan","255 Tanzania","66 Thailand","228 Togo","216 Tunisia",
    "90 Turkey","993 Turkmenistan","256 Uganda","380 Ukraine","971 United Arab Emirates","44 United Kingdom",
    "1 United States","598 Uruguay","998 Uzbekistan","58 Venezuela","84 Vietnam","967 Yemen",
    "260 Zambia","263 Zimbabwe",
  ].map(function (row) {
    var i = row.indexOf(" ");
    return { code: row.slice(0, i), name: row.slice(i + 1) };
  }).sort(function (a, b) { return a.name.localeCompare(b.name); });

  function fillDatalist() {
    var dl = document.getElementById("dial-codes");
    if (!dl || dl.childElementCount) return;
    DIAL_CODES.forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = "+" + c.code + " " + c.name;
      dl.appendChild(opt);
    });
  }

  // Longest dial-code prefix that matches the start of a bare-digit number.
  function matchDialCode(digits) {
    var best = null;
    DIAL_CODES.forEach(function (c) {
      if (digits.startsWith(c.code) && (!best || c.code.length > best.code.length)) best = c;
    });
    return best;
  }

  function initPhoneField(wrap) {
    var picker = wrap.querySelector(".cc-picker");
    var number = wrap.querySelector("input[type=tel]");
    if (!picker || !number) return;

    var raw = number.value.trim();
    if (raw) {
      var match = matchDialCode(raw.replace(/\D/g, ""));
      if (match) {
        picker.value = "+" + match.code + " " + match.name;
        number.value = raw.replace(/\D/g, "").slice(match.code.length);
      }
    } else {
      var def = DIAL_CODES.find(function (c) { return c.code === wrap.dataset.defaultCc; });
      if (def) picker.value = "+" + def.code + " " + def.name;
    }

    var form = wrap.closest("form");
    if (form) {
      form.addEventListener("submit", function () {
        var typed = number.value.trim();
        if (!typed || typed.startsWith("+")) return;
        var ccMatch = picker.value.match(/^\+(\d+)/);
        if (ccMatch) number.value = "+" + ccMatch[1] + " " + typed;
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    fillDatalist();
    document.querySelectorAll("[data-phone]").forEach(initPhoneField);
  });
})();
