/* @ds-bundle: {"format":3,"namespace":"VINDesignSystem_019dcf","components":[],"sourceHashes":{"ui_kits/vin/App.jsx":"9a6ba66c1753","ui_kits/vin/Cards.jsx":"53a3b84b861a","ui_kits/vin/DrugSearch.jsx":"86e713c0db56","ui_kits/vin/Forums.jsx":"64b8b4645407","ui_kits/vin/Hero.jsx":"731ba718ed9a","ui_kits/vin/Hub.jsx":"b23b2c4e3778","ui_kits/vin/Sidebar.jsx":"fade9aa587a3","ui_kits/vin/SiteHeader.jsx":"58a9af1977a1","ui_kits/vspn/App.jsx":"7dc9e751fa27"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.VINDesignSystem_019dcf = window.VINDesignSystem_019dcf || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// ui_kits/vin/App.jsx
try { (() => {
// App.jsx — VIN UI kit demo shell, routes between Hub / Drugs / Forums
function App() {
  const [section, setSection] = React.useState('hub');
  const [activeTab, setActiveTab] = React.useState('Hub');
  const navigate = id => {
    setSection(id);
    if (id === 'hub') setActiveTab('Hub');
    if (id === 'drugs') setActiveTab('Drugs');
    if (id === 'forums') setActiveTab('Forums');
  };
  const onTopNav = t => {
    setActiveTab(t);
    if (t === 'Hub') setSection('hub');
    if (t === 'Drugs') setSection('drugs');
    if (t === 'Forums') setSection('forums');
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "app"
  }, /*#__PURE__*/React.createElement(SiteHeader, {
    product: "VIN",
    activeTab: activeTab,
    onNav: onTopNav
  }), /*#__PURE__*/React.createElement("div", {
    className: "layout"
  }, /*#__PURE__*/React.createElement(Sidebar, {
    section: section,
    onNav: navigate
  }), /*#__PURE__*/React.createElement("main", {
    className: "main reveal reveal--2"
  }, section === 'hub' && /*#__PURE__*/React.createElement(Hub, null), section === 'drugs' && /*#__PURE__*/React.createElement(DrugSearch, null), section === 'forums' && /*#__PURE__*/React.createElement(Forums, null), !['hub', 'drugs', 'forums'].includes(section) && /*#__PURE__*/React.createElement(Hub, null))));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/App.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vin/Cards.jsx
try { (() => {
// Cards.jsx — Fancy + Basic card components
function FancyCard({
  overline,
  title,
  desc,
  tags = [],
  stat,
  statLabel,
  icon,
  link = 'View resource'
}) {
  return /*#__PURE__*/React.createElement("article", {
    className: "fancy-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "fancy-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__top"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__overline"
  }, overline), /*#__PURE__*/React.createElement("h3", {
    className: "fancy-card__title"
  }, title)), icon ? /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__icon"
  }, /*#__PURE__*/React.createElement("img", {
    src: `../../assets/icons/${icon}.svg`,
    alt: ""
  })) : null)), /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "fancy-card__desc"
  }, desc), tags.length ? /*#__PURE__*/React.createElement("ul", {
    className: "fancy-card__tags"
  }, tags.map(t => /*#__PURE__*/React.createElement("li", {
    key: t,
    className: "fancy-card__tag"
  }, t))) : null, stat ? /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__stat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-value"
  }, stat), /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-label"
  }, statLabel)) : null), /*#__PURE__*/React.createElement("footer", {
    className: "fancy-card__footer"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, link, " \u2192")));
}
function BasicCard({
  overline,
  title,
  desc,
  link = 'Read more',
  children
}) {
  return /*#__PURE__*/React.createElement("article", {
    className: "basic-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "basic-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "basic-card__overline"
  }, overline), /*#__PURE__*/React.createElement("h3", {
    className: "basic-card__title"
  }, title)), /*#__PURE__*/React.createElement("div", {
    className: "basic-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "basic-card__desc"
  }, desc), children, /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, link, " \u2192")));
}
window.FancyCard = FancyCard;
window.BasicCard = BasicCard;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/Cards.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vin/DrugSearch.jsx
try { (() => {
// DrugSearch.jsx — clinical drug-handbook search interface
function DrugSearch() {
  const [query, setQuery] = React.useState('');
  const [tab, setTab] = React.useState('All');
  const [selected, setSelected] = React.useState(null);
  const drugs = [{
    name: 'Carprofen',
    class: 'NSAID',
    species: ['Canine'],
    common: 'Rimadyl',
    dose: '2.2 mg/kg PO BID',
    notes: 'Monitor liver enzymes; avoid in cats.'
  }, {
    name: 'Cefpodoxime proxetil',
    class: 'Cephalosporin (3rd gen)',
    species: ['Canine'],
    common: 'Simplicef',
    dose: '5–10 mg/kg PO SID',
    notes: 'Skin/soft tissue infections.'
  }, {
    name: 'Maropitant',
    class: 'NK-1 antagonist',
    species: ['Canine', 'Feline'],
    common: 'Cerenia',
    dose: '1 mg/kg SC SID',
    notes: 'Antiemetic, motion sickness.'
  }, {
    name: 'Pimobendan',
    class: 'Inodilator',
    species: ['Canine'],
    common: 'Vetmedin',
    dose: '0.25 mg/kg PO BID',
    notes: 'CHF, MMVD stage B2 onward.'
  }, {
    name: 'Trazodone',
    class: 'SARI',
    species: ['Canine', 'Feline'],
    common: '—',
    dose: '4–14 mg/kg PO PRN',
    notes: 'Anxiety, post-op rest.'
  }, {
    name: 'Meloxicam',
    class: 'NSAID',
    species: ['Canine', 'Feline'],
    common: 'Metacam',
    dose: '0.1 mg/kg PO SID',
    notes: 'Single-dose use in cats only.'
  }];
  const filtered = drugs.filter(d => {
    const matchTab = tab === 'All' || d.species.includes(tab);
    const matchQ = !query || d.name.toLowerCase().includes(query.toLowerCase()) || d.class.toLowerCase().includes(query.toLowerCase());
    return matchTab && matchQ;
  });
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-overline"
  }, "Clinical Reference"), /*#__PURE__*/React.createElement("h1", {
    className: "page-title"
  }, "Veterinary Drug Handbook"), /*#__PURE__*/React.createElement("p", {
    className: "page-desc"
  }, "4,200+ drug entries with species-specific dosing, contraindications, and clinical notes. Updated quarterly by the VIN editorial board."), /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "search"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/navigate-arrow.svg",
    alt: "",
    width: "14",
    height: "14",
    style: {
      opacity: .5
    }
  }), /*#__PURE__*/React.createElement("input", {
    value: query,
    onChange: e => setQuery(e.target.value),
    placeholder: "Search drug name, class, or indication\u2026"
  })), /*#__PURE__*/React.createElement("button", {
    className: "btn btn--secondary"
  }, "Filters")), /*#__PURE__*/React.createElement("div", {
    className: "tabs"
  }, ['All', 'Canine', 'Feline', 'Equine', 'Bovine'].map(t => /*#__PURE__*/React.createElement("button", {
    key: t,
    className: t === tab ? 'is-active' : '',
    onClick: () => setTab(t)
  }, t))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1.2fr',
      gap: '22px'
    }
  }, /*#__PURE__*/React.createElement("ul", {
    style: {
      listStyle: 'none',
      padding: 0,
      margin: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: '10px'
    }
  }, filtered.map(d => /*#__PURE__*/React.createElement("li", {
    key: d.name
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setSelected(d),
    style: {
      width: '100%',
      textAlign: 'left',
      cursor: 'pointer',
      background: selected?.name === d.name ? '#DDE5ED' : '#FFFFFF',
      border: '1px solid #C9D2DD',
      borderRadius: '8px',
      padding: '14px 16px',
      font: 'inherit',
      color: '#002855'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 800,
      fontSize: '14px'
    }
  }, d.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '11px',
      color: '#4D6995',
      marginTop: '2px'
    }
  }, d.class, " \xB7 ", d.species.join(', ')))))), /*#__PURE__*/React.createElement("div", {
    className: "basic-card",
    style: {
      position: 'sticky',
      top: '92px',
      alignSelf: 'start'
    }
  }, /*#__PURE__*/React.createElement("header", {
    className: "basic-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "basic-card__overline"
  }, selected?.class || 'Select a drug'), /*#__PURE__*/React.createElement("h3", {
    className: "basic-card__title"
  }, selected?.name || '—')), /*#__PURE__*/React.createElement("div", {
    className: "basic-card__body"
  }, selected ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("dl", {
    style: {
      margin: 0,
      display: 'grid',
      gridTemplateColumns: '110px 1fr',
      rowGap: '8px',
      fontSize: '13px'
    }
  }, /*#__PURE__*/React.createElement("dt", {
    style: {
      color: '#4D6995',
      textTransform: 'uppercase',
      letterSpacing: '.06em',
      fontSize: '10px',
      fontWeight: 800,
      alignSelf: 'center'
    }
  }, "Trade name"), /*#__PURE__*/React.createElement("dd", {
    style: {
      margin: 0,
      color: '#002855'
    }
  }, selected.common), /*#__PURE__*/React.createElement("dt", {
    style: {
      color: '#4D6995',
      textTransform: 'uppercase',
      letterSpacing: '.06em',
      fontSize: '10px',
      fontWeight: 800,
      alignSelf: 'center'
    }
  }, "Species"), /*#__PURE__*/React.createElement("dd", {
    style: {
      margin: 0,
      color: '#002855'
    }
  }, selected.species.join(', ')), /*#__PURE__*/React.createElement("dt", {
    style: {
      color: '#4D6995',
      textTransform: 'uppercase',
      letterSpacing: '.06em',
      fontSize: '10px',
      fontWeight: 800,
      alignSelf: 'center'
    }
  }, "Dose"), /*#__PURE__*/React.createElement("dd", {
    style: {
      margin: 0,
      color: '#002855',
      fontFamily: 'Courier New, monospace'
    }
  }, selected.dose), /*#__PURE__*/React.createElement("dt", {
    style: {
      color: '#4D6995',
      textTransform: 'uppercase',
      letterSpacing: '.06em',
      fontSize: '10px',
      fontWeight: 800,
      alignSelf: 'center'
    }
  }, "Notes"), /*#__PURE__*/React.createElement("dd", {
    style: {
      margin: 0,
      color: '#002855'
    }
  }, selected.notes)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '8px',
      marginTop: '14px'
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn--primary"
  }, "Open monograph"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn--secondary"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/save-floppydisk.svg",
    alt: "",
    width: "14",
    height: "14"
  }), " Save"))) : /*#__PURE__*/React.createElement("p", {
    className: "basic-card__desc"
  }, "Pick a drug from the list to see dosing details.")))));
}
window.DrugSearch = DrugSearch;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/DrugSearch.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vin/Forums.jsx
try { (() => {
// Forums.jsx — discussion forum thread list + reader
function Forums() {
  const threads = [{
    board: 'Internal Medicine',
    title: 'Atypical Addisonian crisis presentation in 4yo Std Poodle',
    author: 'Dr. K. Patel',
    replies: 18,
    last: '2h ago',
    unread: true
  }, {
    board: 'Surgery',
    title: 'TPLO vs. CCWO — outcomes for large-breed dogs >50kg',
    author: 'Dr. M. Lin',
    replies: 42,
    last: '5h ago',
    unread: false
  }, {
    board: 'Cardiology',
    title: 'Pimobendan timing in stage B2 MMVD — when to start?',
    author: 'Dr. J. Okafor',
    replies: 27,
    last: '1d ago',
    unread: false
  }, {
    board: 'Behavior',
    title: 'Trazodone + gabapentin combination for fear-aggressive dogs',
    author: 'Dr. S. Reyes',
    replies: 9,
    last: '2d ago',
    unread: false
  }, {
    board: 'Dermatology',
    title: 'Apoquel-resistant atopic patient — next-step protocols',
    author: 'Dr. A. Brennan',
    replies: 14,
    last: '3d ago',
    unread: true
  }];
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "page-overline"
  }, "Community"), /*#__PURE__*/React.createElement("h1", {
    className: "page-title"
  }, "VIN Discussion Forums"), /*#__PURE__*/React.createElement("p", {
    className: "page-desc"
  }, "Peer-to-peer case discussions across 40+ specialty boards. New posts and unread replies are flagged."), /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "search"
  }, /*#__PURE__*/React.createElement("input", {
    placeholder: "Search threads, authors, boards\u2026"
  })), /*#__PURE__*/React.createElement("button", {
    className: "btn btn--primary"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/add-plus.svg",
    alt: "",
    width: "14",
    height: "14",
    style: {
      filter: 'brightness(0) invert(1)'
    }
  }), " New thread")), /*#__PURE__*/React.createElement("ul", {
    style: {
      listStyle: 'none',
      padding: 0,
      margin: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: '0',
      border: '1px solid #C9D2DD',
      borderRadius: '8px',
      overflow: 'hidden',
      background: '#FFFFFF'
    }
  }, threads.map((t, i) => /*#__PURE__*/React.createElement("li", {
    key: i,
    style: {
      borderBottom: i < threads.length - 1 ? '1px solid #C9D2DD' : 'none',
      padding: '16px 20px',
      display: 'grid',
      gridTemplateColumns: '120px 1fr auto',
      gap: '18px',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: '10px',
      fontWeight: 800,
      letterSpacing: '.06em',
      textTransform: 'uppercase',
      color: '#4D6995'
    }
  }, t.board), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '14px',
      fontWeight: 800,
      color: '#002855',
      display: 'flex',
      alignItems: 'center',
      gap: '8px'
    }
  }, t.unread ? /*#__PURE__*/React.createElement("span", {
    style: {
      width: '8px',
      height: '8px',
      borderRadius: '50%',
      background: '#0861CE'
    }
  }) : null, t.title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '12px',
      color: '#4D6995',
      marginTop: '3px'
    }
  }, t.author, " \xB7 ", t.replies, " replies \xB7 last activity ", t.last)), /*#__PURE__*/React.createElement("a", {
    href: "#",
    style: {
      fontSize: '12px',
      color: '#0861CE',
      textDecoration: 'none',
      fontWeight: 500
    }
  }, "Open \u2192")))));
}
window.Forums = Forums;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/Forums.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vin/Hero.jsx
try { (() => {
// Hero.jsx — Navy hero panel with hatch + radial glow
function Hero({
  overline = 'Member Hub',
  title,
  desc,
  primaryAction = 'Go to Hub',
  secondaryAction = 'Learn more',
  onPrimary,
  onSecondary
}) {
  return /*#__PURE__*/React.createElement("section", {
    className: "hero reveal reveal--1"
  }, /*#__PURE__*/React.createElement("div", {
    className: "hero__overline"
  }, overline), /*#__PURE__*/React.createElement("h1", {
    className: "hero__title"
  }, title), /*#__PURE__*/React.createElement("p", {
    className: "hero__desc"
  }, desc), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '10px'
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn--on-dark",
    onClick: onPrimary
  }, primaryAction), /*#__PURE__*/React.createElement("button", {
    className: "btn btn--tertiary",
    style: {
      color: '#DDE5ED'
    },
    onClick: onSecondary
  }, secondaryAction, " \u2192")));
}
function Banner({
  kind = 'warning',
  children
}) {
  const palette = {
    warning: {
      bg: '#E8E3D2',
      border: '#B75D04',
      icon: 'info-question'
    },
    info: {
      bg: '#DDE5ED',
      border: '#0861CE',
      icon: 'info-question'
    },
    success: {
      bg: '#C2E9F1',
      border: '#007D61',
      icon: 'info-question'
    }
  }[kind];
  return /*#__PURE__*/React.createElement("div", {
    className: "banner",
    style: {
      background: palette.bg,
      borderLeftColor: palette.border
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `../../assets/icons/${palette.icon}.svg`,
    alt: ""
  }), /*#__PURE__*/React.createElement("div", null, children));
}
window.Hero = Hero;
window.Banner = Banner;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/Hero.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vin/Hub.jsx
try { (() => {
// Hub.jsx — Hub landing page composing Hero + sections of cards
function Hub() {
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Hero, {
    overline: "Welcome back, Dr. Reyes",
    title: "Member Resource Hub",
    desc: "Drug references, image libraries, CE webinars, and the largest peer community in veterinary medicine \u2014 all in one place.",
    primaryAction: "Go to Hub",
    secondaryAction: "What's new"
  }), /*#__PURE__*/React.createElement(Banner, {
    kind: "warning"
  }, /*#__PURE__*/React.createElement("strong", null, "System Maintenance:"), " Scheduled downtime Sunday, April 6, 2\u20134 AM CT. No action required."), /*#__PURE__*/React.createElement("div", {
    className: "section-heading"
  }, /*#__PURE__*/React.createElement("h2", {
    className: "section-heading__title"
  }, "Clinical Resources"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "section-heading__link"
  }, "View all \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "grid"
  }, /*#__PURE__*/React.createElement(FancyCard, {
    overline: "Clinical Resources",
    title: "Veterinary Drug Handbook",
    desc: "Comprehensive pharmacological reference with dosing, contraindications, and species-specific considerations.",
    tags: ["Pharmacology", "Reference"],
    stat: "4,200+",
    statLabel: "drug entries",
    icon: "save-floppydisk"
  }), /*#__PURE__*/React.createElement(FancyCard, {
    overline: "Clinical Resources",
    title: "Image Library",
    desc: "Diagnostic imaging, dermatology plates, and surgical reference photos. Searchable by species and modality.",
    tags: ["Imaging", "Reference"],
    stat: "120k+",
    statLabel: "annotated images",
    icon: "navigate-arrow"
  }), /*#__PURE__*/React.createElement(FancyCard, {
    overline: "Clinical Resources",
    title: "Surgical Techniques Webinar",
    desc: "Live and on-demand surgical demonstrations from board-certified specialists. Earn CE credits while you learn.",
    tags: ["Surgery", "CE"],
    stat: "1.5",
    statLabel: "CE hours available",
    icon: "edit-penpaper"
  })), /*#__PURE__*/React.createElement("div", {
    className: "section-heading"
  }, /*#__PURE__*/React.createElement("h2", {
    className: "section-heading__title"
  }, "Community & Updates"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "section-heading__link"
  }, "View all \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "grid"
  }, /*#__PURE__*/React.createElement(BasicCard, {
    overline: "Announcements",
    title: "Search Now Includes Images",
    desc: "Drug-handbook search results now surface relevant clinical images alongside text. Available on web and mobile."
  }), /*#__PURE__*/React.createElement(BasicCard, {
    overline: "Platform Updates",
    title: "System Maintenance Window",
    desc: "Scheduled downtime on Sunday, April 6 from 2\u20134 AM CT. All member services will be temporarily unavailable."
  }), /*#__PURE__*/React.createElement(BasicCard, {
    overline: "Quick Links",
    title: "VIN Community Forums",
    desc: "100,000+ active members across 40+ specialty boards. Post a case, search archives, or read this week's most-active threads."
  })));
}
window.Hub = Hub;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/Hub.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vin/Sidebar.jsx
try { (() => {
// Sidebar.jsx — left nav with grouped links, used on Hub + Drugs + CE pages
function Sidebar({
  section = 'hub',
  onNav
}) {
  const groups = [{
    heading: 'Clinical',
    items: [{
      id: 'drugs',
      label: 'Drug Handbook',
      icon: 'save-floppydisk'
    }, {
      id: 'images',
      label: 'Image Library',
      icon: 'navigate-arrow'
    }, {
      id: 'protocols',
      label: 'Protocols',
      icon: 'edit-penpaper'
    }]
  }, {
    heading: 'Education',
    items: [{
      id: 'webinars',
      label: 'CE Webinars',
      icon: 'print-printer'
    }, {
      id: 'rounds',
      label: 'Rounds',
      icon: 'info-question'
    }, {
      id: 'transcripts',
      label: 'Transcripts',
      icon: 'edit-penpaper'
    }]
  }, {
    heading: 'Community',
    items: [{
      id: 'forums',
      label: 'Discussion Forums',
      icon: 'add-plus'
    }, {
      id: 'messages',
      label: 'Direct Messages',
      icon: 'navigate-arrow'
    }]
  }, {
    heading: 'Account',
    items: [{
      id: 'membership',
      label: 'Membership',
      icon: 'pad-lock'
    }, {
      id: 'billing',
      label: 'Billing',
      icon: 'save-floppydisk'
    }, {
      id: 'preferences',
      label: 'Preferences',
      icon: 'edit-penpaper'
    }]
  }];
  return /*#__PURE__*/React.createElement("aside", {
    className: "sidebar"
  }, groups.map(g => /*#__PURE__*/React.createElement(React.Fragment, {
    key: g.heading
  }, /*#__PURE__*/React.createElement("div", {
    className: "sidebar__heading"
  }, g.heading), /*#__PURE__*/React.createElement("ul", {
    className: "sidebar__list"
  }, g.items.map(it => /*#__PURE__*/React.createElement("li", {
    key: it.id,
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: it.id === section ? 'is-active' : '',
    onClick: e => {
      e.preventDefault();
      onNav?.(it.id);
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `../../assets/icons/${it.icon}.svg`,
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, it.label))))))));
}
window.Sidebar = Sidebar;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/Sidebar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vin/SiteHeader.jsx
try { (() => {
// SiteHeader.jsx — VIN top nav with brand + product label + nav + user pill
function SiteHeader({
  product = 'VIN',
  activeTab = 'Hub',
  onNav
}) {
  const tabs = ['Hub', 'Drugs', 'Library', 'CE', 'Forums', 'Account'];
  return /*#__PURE__*/React.createElement("header", {
    className: "site-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "site-header__brand"
  }, /*#__PURE__*/React.createElement("img", {
    src: product === 'VSPN' ? '../../assets/VSPN-light.svg' : '../../assets/VIN-light.svg',
    alt: product,
    style: {
      height: '28px',
      filter: 'none'
    }
  })), /*#__PURE__*/React.createElement("span", {
    className: "site-header__divider"
  }), /*#__PURE__*/React.createElement("span", {
    className: "site-header__product"
  }, product === 'VSPN' ? 'Support Personnel Network' : 'Veterinary Information Network'), /*#__PURE__*/React.createElement("nav", {
    className: "site-header__nav"
  }, tabs.map(t => /*#__PURE__*/React.createElement("a", {
    key: t,
    href: "#",
    className: t === activeTab ? 'is-active' : '',
    onClick: e => {
      e.preventDefault();
      onNav?.(t);
    }
  }, t))), /*#__PURE__*/React.createElement("div", {
    className: "site-header__user"
  }, /*#__PURE__*/React.createElement("span", {
    className: "site-header__avatar"
  }, "DR"), /*#__PURE__*/React.createElement("span", null, "Dr. Reyes")));
}
window.SiteHeader = SiteHeader;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vin/SiteHeader.jsx", error: String((e && e.message) || e) }); }

// ui_kits/vspn/App.jsx
try { (() => {
// VSPN UI Kit — sister site, green primary, support-personnel framing
function App() {
  return /*#__PURE__*/React.createElement("div", {
    className: "app"
  }, /*#__PURE__*/React.createElement("header", {
    className: "site-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "site-header__brand"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/VSPN-light.svg",
    alt: "VSPN",
    style: {
      height: '28px'
    }
  })), /*#__PURE__*/React.createElement("span", {
    className: "site-header__divider"
  }), /*#__PURE__*/React.createElement("span", {
    className: "site-header__product"
  }, "Veterinary Support Personnel Network"), /*#__PURE__*/React.createElement("nav", {
    className: "site-header__nav"
  }, ['Hub', 'Skills', 'CE', 'Forums', 'Account'].map((t, i) => /*#__PURE__*/React.createElement("a", {
    key: t,
    href: "#",
    className: i === 0 ? 'is-active' : ''
  }, t))), /*#__PURE__*/React.createElement("div", {
    className: "site-header__user"
  }, /*#__PURE__*/React.createElement("span", {
    className: "site-header__avatar",
    style: {
      background: '#B9975B'
    }
  }, "JM"), /*#__PURE__*/React.createElement("span", null, "Jamie M., RVT"))), /*#__PURE__*/React.createElement("div", {
    className: "layout"
  }, /*#__PURE__*/React.createElement("aside", {
    className: "sidebar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "sidebar__heading"
  }, "Skills & Reference"), /*#__PURE__*/React.createElement("ul", {
    className: "sidebar__list"
  }, /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "is-active"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/save-floppydisk.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Skill Library"))), /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/edit-penpaper.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Procedures"))), /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/info-question.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Quick Reference")))), /*#__PURE__*/React.createElement("div", {
    className: "sidebar__heading"
  }, "Education"), /*#__PURE__*/React.createElement("ul", {
    className: "sidebar__list"
  }, /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/print-printer.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "CE Courses"))), /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/edit-penpaper.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Transcripts")))), /*#__PURE__*/React.createElement("div", {
    className: "sidebar__heading"
  }, "Community"), /*#__PURE__*/React.createElement("ul", {
    className: "sidebar__list"
  }, /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/add-plus.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Tech Forums"))), /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/navigate-arrow.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Direct Messages")))), /*#__PURE__*/React.createElement("div", {
    className: "sidebar__heading"
  }, "Account"), /*#__PURE__*/React.createElement("ul", {
    className: "sidebar__list"
  }, /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/pad-lock.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Membership"))), /*#__PURE__*/React.createElement("li", {
    className: "sidebar__item"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/save-floppydisk.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", null, "Billing"))))), /*#__PURE__*/React.createElement("main", {
    className: "main reveal reveal--2"
  }, /*#__PURE__*/React.createElement("section", {
    className: "hero reveal reveal--1"
  }, /*#__PURE__*/React.createElement("div", {
    className: "hero__overline"
  }, "Welcome back, Jamie"), /*#__PURE__*/React.createElement("h1", {
    className: "hero__title"
  }, "VSPN Skills Hub"), /*#__PURE__*/React.createElement("p", {
    className: "hero__desc"
  }, "Continuing education, peer-reviewed skill protocols, and a tech-only community of 30,000+ credentialed support personnel."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '10px'
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn--on-dark"
  }, "Browse skills"), /*#__PURE__*/React.createElement("button", {
    className: "btn btn--tertiary",
    style: {
      color: '#DDE5ED'
    }
  }, "What's new \u2192"))), /*#__PURE__*/React.createElement("div", {
    className: "banner",
    style: {
      background: '#C2E9F1',
      borderLeftColor: '#0097A9'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/info-question.svg",
    alt: ""
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("strong", null, "New release:"), " Skill assessment checklists are now downloadable as PDF. Find them on each skill page.")), /*#__PURE__*/React.createElement("div", {
    className: "section-heading"
  }, /*#__PURE__*/React.createElement("h2", {
    className: "section-heading__title"
  }, "Featured Skills"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "section-heading__link"
  }, "View library \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "grid"
  }, /*#__PURE__*/React.createElement("article", {
    className: "fancy-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "fancy-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__top"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__overline"
  }, "Anesthesia"), /*#__PURE__*/React.createElement("h3", {
    className: "fancy-card__title"
  }, "IV Catheter Placement")), /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__icon"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/edit-penpaper.svg",
    alt: ""
  })))), /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "fancy-card__desc"
  }, "Step-by-step protocol for cephalic and saphenous IV catheter placement, including troubleshooting and patient-prep checklists."), /*#__PURE__*/React.createElement("ul", {
    className: "fancy-card__tags"
  }, /*#__PURE__*/React.createElement("li", {
    className: "fancy-card__tag"
  }, "Anesthesia"), /*#__PURE__*/React.createElement("li", {
    className: "fancy-card__tag"
  }, "Skill")), /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__stat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-value"
  }, "12"), /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-label"
  }, "min read"))), /*#__PURE__*/React.createElement("footer", {
    className: "fancy-card__footer"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, "View skill \u2192"))), /*#__PURE__*/React.createElement("article", {
    className: "fancy-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "fancy-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__top"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__overline"
  }, "Diagnostics"), /*#__PURE__*/React.createElement("h3", {
    className: "fancy-card__title"
  }, "Blood Smear Evaluation")), /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__icon"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/navigate-arrow.svg",
    alt: ""
  })))), /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "fancy-card__desc"
  }, "Identifying common cell morphologies, parasites, and artifacts on canine and feline blood smears."), /*#__PURE__*/React.createElement("ul", {
    className: "fancy-card__tags"
  }, /*#__PURE__*/React.createElement("li", {
    className: "fancy-card__tag"
  }, "Diagnostics"), /*#__PURE__*/React.createElement("li", {
    className: "fancy-card__tag"
  }, "Cytology")), /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__stat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-value"
  }, "1.0"), /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-label"
  }, "CE hour"))), /*#__PURE__*/React.createElement("footer", {
    className: "fancy-card__footer"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, "Start course \u2192"))), /*#__PURE__*/React.createElement("article", {
    className: "fancy-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "fancy-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__top"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__overline"
  }, "Patient Care"), /*#__PURE__*/React.createElement("h3", {
    className: "fancy-card__title"
  }, "Pain Score Assessment")), /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__icon"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/info-question.svg",
    alt: ""
  })))), /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "fancy-card__desc"
  }, "Glasgow Composite Pain Scale and Feline Grimace Scale walkthroughs with scoring rubrics and case examples."), /*#__PURE__*/React.createElement("ul", {
    className: "fancy-card__tags"
  }, /*#__PURE__*/React.createElement("li", {
    className: "fancy-card__tag"
  }, "Patient Care"), /*#__PURE__*/React.createElement("li", {
    className: "fancy-card__tag"
  }, "Reference")), /*#__PURE__*/React.createElement("div", {
    className: "fancy-card__stat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-value"
  }, "300+"), /*#__PURE__*/React.createElement("span", {
    className: "fancy-card__stat-label"
  }, "case examples"))), /*#__PURE__*/React.createElement("footer", {
    className: "fancy-card__footer"
  }, /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, "Read more \u2192")))), /*#__PURE__*/React.createElement("div", {
    className: "section-heading"
  }, /*#__PURE__*/React.createElement("h2", {
    className: "section-heading__title"
  }, "Latest from the Tech Forums"), /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "section-heading__link"
  }, "View all \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "grid"
  }, /*#__PURE__*/React.createElement("article", {
    className: "basic-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "basic-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "basic-card__overline"
  }, "Pharmacy"), /*#__PURE__*/React.createElement("h3", {
    className: "basic-card__title"
  }, "Calculating CRI rates \u2014 common mistakes")), /*#__PURE__*/React.createElement("div", {
    className: "basic-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "basic-card__desc"
  }, "A quick refresher on dimensional analysis and the most common errors in constant-rate-infusion calculations."), /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, "Read thread \u2192"))), /*#__PURE__*/React.createElement("article", {
    className: "basic-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "basic-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "basic-card__overline"
  }, "Anesthesia"), /*#__PURE__*/React.createElement("h3", {
    className: "basic-card__title"
  }, "Capnography: troubleshooting low ETCO\u2082")), /*#__PURE__*/React.createElement("div", {
    className: "basic-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "basic-card__desc"
  }, "Differential causes and how to react when ETCO\u2082 drops mid-procedure on a stable patient."), /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, "Read thread \u2192"))), /*#__PURE__*/React.createElement("article", {
    className: "basic-card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "basic-card__header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "basic-card__overline"
  }, "Career"), /*#__PURE__*/React.createElement("h3", {
    className: "basic-card__title"
  }, "Switching from GP to specialty \u2014 what to know")), /*#__PURE__*/React.createElement("div", {
    className: "basic-card__body"
  }, /*#__PURE__*/React.createElement("p", {
    className: "basic-card__desc"
  }, "Tech-to-tech advice on transitioning from general practice to a specialty role."), /*#__PURE__*/React.createElement("a", {
    href: "#",
    className: "fancy-card__link"
  }, "Read thread \u2192")))))));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/vspn/App.jsx", error: String((e && e.message) || e) }); }

})();
