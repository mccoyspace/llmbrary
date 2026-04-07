#!/usr/bin/env python3
"""
generate_wiki.py — Generate synthesized thematic wiki pages from catalog.json.

Inspired by Karpathy's LLM Knowledge Base pattern: instead of per-book entries,
these pages synthesize across multiple books to capture intellectual threads
that run through the collection.

Usage:
    python3 scripts/generate_wiki.py
"""

import json
import re
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"
WIKI_DIR = REPO_ROOT / "wiki"


def load_catalog() -> list[dict]:
    with open(CATALOG_PATH) as f:
        return json.load(f)


def slug(title: str) -> str:
    """Convert a page title to a filename-safe slug."""
    s = title.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def build_indices(catalog: list[dict]) -> dict:
    """Build various lookup indices from the catalog."""
    by_title = {b["title"]: b for b in catalog}
    by_theme = defaultdict(list)
    by_author = defaultdict(list)
    conversation_graph = defaultdict(set)

    for b in catalog:
        for t in b.get("themes", []):
            by_theme[t.lower()].append(b)
        author = b.get("author") or ""
        if author:
            by_author[author].append(b)
        for c in b.get("in_conversation_with", []):
            conversation_graph[b["title"]].add(c)
            if c in by_title:
                conversation_graph[c].add(b["title"])

    return {
        "by_title": by_title,
        "by_theme": by_theme,
        "by_author": by_author,
        "conversation_graph": conversation_graph,
    }


def find_books(catalog: list[dict], indices: dict, *,
               themes: list[str] = None,
               title_keywords: list[str] = None,
               authors: list[str] = None,
               min_score: int = 1) -> list[tuple[dict, int]]:
    """Score and return books matching criteria, sorted by relevance."""
    scores = defaultdict(int)
    for b in catalog:
        title_lower = b["title"].lower()
        author_lower = (b.get("author") or "").lower()
        book_themes = [t.lower() for t in b.get("themes", [])]
        synopsis = b.get("synopsis", "").lower()
        combined = f"{title_lower} {author_lower} {' '.join(book_themes)} {synopsis}"

        if themes:
            for t in themes:
                if t.lower() in book_themes:
                    scores[b["title"]] += 5
                elif t.lower() in combined:
                    scores[b["title"]] += 2

        if title_keywords:
            for kw in title_keywords:
                if kw.lower() in title_lower:
                    scores[b["title"]] += 8
                elif kw.lower() in combined:
                    scores[b["title"]] += 2

        if authors:
            for a in authors:
                if a.lower() in author_lower:
                    scores[b["title"]] += 10

    results = [(indices["by_title"][t], s) for t, s in scores.items() if s >= min_score]
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def format_book_ref(b: dict) -> str:
    """Format a book as a brief inline reference."""
    author = b.get("author") or ""
    year = b.get("year")
    parts = [f"*{b['title']}*"]
    if author:
        parts[0] += f" ({author}"
        if year:
            parts[0] += f", {year}"
        parts[0] += ")"
    elif year:
        parts[0] += f" ({year})"
    return parts[0]


def cross_link(page_title: str, all_pages: dict[str, str]) -> str:
    """Generate a markdown link to another wiki page."""
    s = slug(page_title)
    return f"[{page_title}]({s}.md)"


# ---------------------------------------------------------------------------
# Wiki page definitions
# Each function returns (title, filename, content)
# ---------------------------------------------------------------------------

WIKI_PAGES = []


def wiki_page(fn):
    WIKI_PAGES.append(fn)
    return fn


@wiki_page
def page_video_art(catalog, indices):
    title = "Video Art and Media Theory"
    books = find_books(catalog, indices,
                       themes=["video art", "moving image", "time-based media", "media art"],
                       title_keywords=["Paik", "Viola", "Gary Hill", "Joan Jonas", "Videofreex",
                                       "Vostell", "Broken Screen", "Video", "Echo"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The collection's video art holdings trace the medium from its countercultural origins through its institutionalization as a dominant contemporary art form. The founding generation is well represented: {format_book_ref(indices['by_title']['Nam June Paik: Video Time — Video Space'])} documents the artist who first turned a television into a canvas, while {format_book_ref(indices['by_title']['Videofreex'])} captures the radical community-media movement that saw video as a tool for social transformation rather than gallery display. These two poles — video as art object and video as democratic medium — define a tension that runs through the entire collection.

The middle generation appears through monographs on artists who pushed the medium toward philosophical and phenomenological investigation. {format_book_ref(indices['by_title']['Bill Viola'])} and the companion volume {format_book_ref(indices['by_title'].get('Bill Viola | Michelangelo', indices['by_title']['Bill Viola']))} position Viola's durational works within a tradition running from Renaissance painting to Eastern spirituality. {format_book_ref(indices['by_title']['Gary Hill'])} represents the linguistically-inflected branch where video becomes a medium for exploring the gap between language and perception. {format_book_ref(indices['by_title']['Joan Jonas: Good Night Good Morning'])} bridges video and performance, while {format_book_ref(indices['by_title']['Broken Screen'])} maps the broader cultural shift toward non-linear moving image narrative.

The theoretical scaffolding comes from multiple directions. {format_book_ref(indices['by_title']['A History of Video Art'])} provides the historical survey, and {format_book_ref(indices['by_title']['Vitamin V: Video and the Moving Image in Contemporary Art'])} offers a snapshot of the field's contemporary breadth. The connection to film theory is explicit through {format_book_ref(indices['by_title']['Cinema 2: The Time-Image'])}, where Deleuze's concept of the time-image provides philosophical grounding for video art's temporal experiments. The collection also includes {format_book_ref(indices['by_title']['Tiny Funny Big and Sad'])}, a database cinema project that sits at the intersection of video, conceptual art, and digital media — connecting this thread directly to [Digital Art and Blockchain Culture](digital-art-and-blockchain-culture.md) and [Conceptual and Rule-Based Art](conceptual-and-rule-based-art.md).

See also: [French Theory in the American Art World](french-theory-in-the-american-art-world.md), [Fluxus and Neo-Dada](fluxus-and-neo-dada.md), [Sound, Listening, and Experimental Music](sound-listening-and-experimental-music.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_situationist(catalog, indices):
    title = "Situationism, Spectacle, and Everyday Life"
    books = find_books(catalog, indices,
                       themes=["Situationism", "spectacle", "everyday life", "détournement"],
                       title_keywords=["Debord", "Situationist", "Everyday Life", "Egress",
                                       "All That Is Solid", "Spectacle", "Rancière"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

Guy Debord's {format_book_ref(indices['by_title']['La Société du Spectacle'])} anchors one of the collection's deepest intellectual threads — the critique of spectacle as the organizing logic of capitalist society. The primary texts are here: Debord's treatise alongside the {format_book_ref(indices['by_title']['Situationist International Anthology'])}, which documents the full range of SI activity from urban drift to revolutionary theory. But the collection extends this thread forward and backward in revealing ways, connecting Situationist thought to both its theoretical ancestors and its contemporary inheritors.

The backward connections run through Walter Benjamin and the Frankfurt School. {format_book_ref(indices['by_title']['On Walter Benjamin'])} and {format_book_ref(indices['by_title']['The Everyday Life Reader'])} establish the intellectual genealogy: from Benjamin's analysis of commodity culture and the flâneur through Lefebvre's critique of everyday life to Debord's totalizing vision of the spectacle. {format_book_ref(indices['by_title']['All That Is Solid Melts into Air'])} by Marshall Berman provides the broader frame of modernity within which spectacle theory operates, while {format_book_ref(indices['by_title']['Critique of Commodity Aesthetics'])} extends the Marxist analysis of appearance into consumer culture.

The forward connections are equally rich. {format_book_ref(indices['by_title']['Egress'])} traces the line from Debord through Mark Fisher's "capitalist realism" to contemporary cultural theory, while {format_book_ref(indices['by_title']['The Time of the Landscape'])} by Rancière offers an aesthetic philosophy that both inherits and revises the Situationist project. The thread also connects to the collection's media theory holdings — {format_book_ref(indices['by_title']['Body Invaders'])} and {format_book_ref(indices['by_title']['Electronic Culture'])} update spectacle critique for the digital age, leading toward the [Media Theory and Digital Culture](media-theory-and-digital-culture.md) cluster. The social practice art documented in {format_book_ref(indices['by_title']['Living as Form'])} can be read as a contemporary response to the SI's demand that art dissolve into life.

See also: [French Theory in the American Art World](french-theory-in-the-american-art-world.md), [Political Philosophy and Radical Thought](political-philosophy-and-radical-thought.md), [Media Theory and Digital Culture](media-theory-and-digital-culture.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_beat(catalog, indices):
    title = "Beat Literature and the Burroughs Corpus"
    books = find_books(catalog, indices,
                       themes=["Beat Generation", "cut-up technique", "counterculture"],
                       title_keywords=["Burroughs", "Gysin", "Ginsberg", "Howl", "Naked Lunch",
                                       "Junky", "Queer"],
                       authors=["William S. Burroughs"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The collection contains what amounts to a dedicated Burroughs shelf — seven titles spanning his career from the early autobiographical {format_book_ref(indices['by_title']['Junky'])} and {format_book_ref(indices['by_title']['Queer'])} through the revolutionary {format_book_ref(indices['by_title']['Naked Lunch'])} to the later experimental works like {format_book_ref(indices['by_title']['The Wild Boys'])} and {format_book_ref(indices['by_title']['Exterminator!'])}. The inclusion of {format_book_ref(indices['by_title']['The Letters of William S. Burroughs'])} and {format_book_ref(indices['by_title']['The Burroughs File'])} suggests an interest in Burroughs not just as a novelist but as a figure whose entire textual output constitutes a kind of experimental practice — a position reinforced by the presence of {format_book_ref(indices['by_title']['Brion Gysin: Tuning in to the Multimedia Age'])}, documenting the collaborator who pushed Burroughs toward the cut-up technique.

The cut-up method is the conceptual bridge between Beat literature and the collection's broader interest in rule-based and algorithmic art. Burroughs and Gysin's approach to text — slicing, recombining, treating language as material to be manipulated — anticipates the generative and database-driven art practices documented elsewhere in the library. The line from cut-ups to {format_book_ref(indices['by_title']['Processing'])} and {format_book_ref(indices['by_title']['Logical Conclusions: 40 Years of Rule-Based Art'])} is direct: all share the premise that systematic procedures applied to cultural material can produce meaning that no single author could intend. See [Conceptual and Rule-Based Art](conceptual-and-rule-based-art.md) for this thread.

Beyond Burroughs, the Beat presence includes {format_book_ref(indices['by_title']['Howl'])} by Allen Ginsberg, connecting to the broader countercultural current that also surfaces in {format_book_ref(indices['by_title']['Blueprint for Counter Education'])} and the [Counterculture and Radical Pedagogy](counterculture-and-radical-pedagogy.md) cluster. The Beats also connect to the collection's interest in bodily transgression and altered states through figures like Henry Miller ({format_book_ref(indices['by_title']['Sexus'])}, {format_book_ref(indices['by_title']['Plexus'])}) and the broader thread of [Existentialism and European Literary Voices](existentialism-and-european-literary-voices.md).

See also: [American Literary Traditions](american-literary-traditions.md), [Counterculture and Radical Pedagogy](counterculture-and-radical-pedagogy.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_digital_art(catalog, indices):
    title = "Digital Art and Blockchain Culture"
    books = find_books(catalog, indices,
                       themes=["digital art", "NFTs", "blockchain", "crypto art", "net art",
                               "new media art", "creative coding", "digital culture",
                               "computational art"],
                       title_keywords=["NFT", "Processing", "Rhizome", "Surfing", "Satoshi",
                                       "Digital", "New Media"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The collection contains a substantial cluster of texts mapping the intersection of art and digital technology. The foundational surveys are here — {format_book_ref(indices['by_title']['Digital Art'])} by Christiane Paul and {format_book_ref(indices['by_title']['New Media Art'])} by Mark Tribe and Reena Jana — alongside more recent entries like {format_book_ref(indices['by_title']['On NFTs'])} and {format_book_ref(indices['by_title']['Surfing with Satoshi'])}, which document the crypto art movement. {format_book_ref(indices['by_title']['Processing'])} by Casey Reas and Ben Fry represents the creative coding tools that became infrastructure for a generation of computational artists.

What distinguishes this cluster from a simple "digital art survey" shelf is how it connects to the collection's critical theory holdings. {format_book_ref(indices['by_title']['Protocol'])} by Alexander Galloway analyzes the internet's control structures through Deleuzian philosophy, linking digital culture directly to the [French Theory in the American Art World](french-theory-in-the-american-art-world.md) thread. {format_book_ref(indices['by_title']['The Social Media Reader'])} and {format_book_ref(indices['by_title']['Electronic Culture'])} provide the media-critical framework, while {format_book_ref(indices['by_title']['Imaginary Futures'])} historicizes Silicon Valley utopianism as Cold War ideology. The collection doesn't treat digital art as a self-contained category but as the latest episode in longer histories of technology, spectacle, and cultural production.

The collection also includes {format_book_ref(indices['by_title']['Tiny Funny Big and Sad'])}, a database cinema project, and {format_book_ref(indices['by_title']['Collective Intelligence'])} by Agnieszka Kurant explores the emergence and distributed authorship themes that connect to blockchain's decentralized logic. The crypto-political thread extends through {format_book_ref(indices['by_title']['Cryptocommunism'])} into broader questions about technology and political economy explored in [Political Philosophy and Radical Thought](political-philosophy-and-radical-thought.md).

See also: [Media Theory and Digital Culture](media-theory-and-digital-culture.md), [Video Art and Media Theory](video-art-and-media-theory.md), [Conceptual and Rule-Based Art](conceptual-and-rule-based-art.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_french_theory(catalog, indices):
    title = "French Theory in the American Art World"
    books = find_books(catalog, indices,
                       themes=["French theory", "Deleuze", "Foucault", "phenomenology",
                               "existentialism", "structuralism", "hermeneutics",
                               "continental philosophy"],
                       title_keywords=["Deleuze", "Foucault", "Rancière", "Baudrillard",
                                       "Merleau-Ponty", "Sartre", "Barthes", "Ricoeur",
                                       "Debord", "Bataille"],
                       authors=["Deleuze", "Foucault", "Rancière", "Barthes", "Sartre",
                                "Merleau-Ponty", "Camus", "Beauvoir", "Bataille"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The collection holds a substantial body of French theoretical writing, but its arrangement reveals how these texts function as tools for art-making rather than purely academic philosophy. Deleuze appears in three forms: the philosophical reader ({format_book_ref(indices['by_title']['The Deleuze Reader'])}), the collaborative manifesto ({format_book_ref(indices['by_title']['What Is Philosophy?'])}), and the applied film theory ({format_book_ref(indices['by_title']['Cinema 2: The Time-Image'])}). This spread — from pure philosophy through aesthetics to media analysis — is characteristic of how the collection positions French thought: always in dialogue with practice.

Foucault is present through {format_book_ref(indices['by_title']['Power/Knowledge'])} and the secondary literature on his work, connecting to the political philosophy cluster through questions of power, knowledge, and institutional critique. Barthes appears via {format_book_ref(indices['by_title']['S/Z'])}, the masterclass in close reading that influenced a generation of text-based and conceptual artists. The phenomenological tradition is deep: {format_book_ref(indices['by_title']["Phénoménologie de la perception"])} by Merleau-Ponty, {format_book_ref(indices['by_title']["L'Être et le Néant"])} by Sartre, and {format_book_ref(indices['by_title']["De l'interprétation"])} by Ricoeur form a core that informs the collection's interest in perception, embodiment, and interpretation — themes that directly feed into the video and installation art holdings.

The existentialist literary tradition adds another dimension: Camus ({format_book_ref(indices['by_title']["L'Étranger"])}, {format_book_ref(indices['by_title']["Noces suivi de L'Été"])}), Beauvoir ({format_book_ref(indices['by_title']['The Woman Destroyed'])}), Genet ({format_book_ref(indices['by_title']['Le Balcon'])}, {format_book_ref(indices['by_title']['Miracle de la Rose'])}), and Bataille ({format_book_ref(indices['by_title']['Visions of Excess'])}, {format_book_ref(indices['by_title']['Theory of Religion'])}). These are not merely literary holdings but represent the existentialist engagement with transgression, embodiment, and the sacred that connects to [Myth, Spirituality, and the Sacred](myth-spirituality-and-the-sacred.md) and the performance art thread in [Fluxus and Neo-Dada](fluxus-and-neo-dada.md). The Rancière holdings ({format_book_ref(indices['by_title']['The Time of the Landscape'])}) extend French aesthetic philosophy into the present, bridging to the [Situationism, Spectacle, and Everyday Life](situationism-spectacle-and-everyday-life.md) thread.

See also: [Situationism, Spectacle, and Everyday Life](situationism-spectacle-and-everyday-life.md), [Art Criticism and the Philosophy of Art](art-criticism-and-the-philosophy-of-art.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_fluxus(catalog, indices):
    title = "Fluxus and Neo-Dada"
    books = find_books(catalog, indices,
                       themes=["Fluxus", "happenings", "Neo-Dada", "instruction art",
                               "performance art", "body art"],
                       title_keywords=["Beuys", "Rauschenberg", "Ono", "Grapefruit",
                                       "Vostell", "Paik", "Acconci", "Niki de Saint Phalle",
                                       "Dieter Roth", "Performance"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The Fluxus and Neo-Dada holdings constitute one of the collection's densest clusters, reflecting an artistic tradition that has profoundly shaped contemporary practice from performance art to digital media. The key figures are well represented: {format_book_ref(indices['by_title']['Joseph Beuys'])} documents the social sculptor who pushed Fluxus toward political mythmaking; {format_book_ref(indices['by_title']['Nam June Paik: Video Time — Video Space'])} covers the artist who carried Fluxus energy into the new medium of video; {format_book_ref(indices['by_title']['Grapefruit'])} by Yoko Ono remains the purest expression of instruction-based art's radical minimalism; and {format_book_ref(indices['by_title']['Vostell'])} represents the décollage and happening tradition.

{format_book_ref(indices['by_title']['Robert Rauschenberg'])} and {format_book_ref(indices['by_title']['Dieter Roth'])} mark the Neo-Dada branch — artists who collapsed boundaries between art and everyday materials through accumulation, combination, and deliberate impermanence. Roth's embrace of decay and process anticipates contemporary concerns with entropy and sustainability, while Rauschenberg's Combines opened the door to the multimedia installations that dominate contemporary art. The performance art thread extends through {format_book_ref(indices['by_title']['Vito Acconci'])}, {format_book_ref(indices['by_title']['Performance Anthology'])}, and {format_book_ref(indices['by_title']['Artaud Anthology'])} — the last connecting Fluxus performance back to its pre-war theatrical roots in Artaud's Theater of Cruelty.

What makes this cluster particularly significant within the collection is its connective tissue to other threads. The instruction-based dimension of Fluxus (Ono's scores, Beuys's actions) leads directly to [Conceptual and Rule-Based Art](conceptual-and-rule-based-art.md). The intermedia experiments of Paik and Vostell prefigure [Video Art and Media Theory](video-art-and-media-theory.md). And the Fluxus insistence on dissolving the boundary between art and life connects to both the [Situationism, Spectacle, and Everyday Life](situationism-spectacle-and-everyday-life.md) thread and the social practice documented in {format_book_ref(indices['by_title']['Living as Form'])}.

See also: [Sculpture, Installation, and Materiality](sculpture-installation-and-materiality.md), [Video Art and Media Theory](video-art-and-media-theory.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_vernacular(catalog, indices):
    title = "Vernacular Cultural Forms"
    books = find_books(catalog, indices,
                       themes=["shape-note singing", "oral tradition", "folk art", "craft",
                               "hymnody", "knitting", "folklore", "folk music",
                               "congregational singing", "indigenous culture"],
                       title_keywords=["Sacred Harp", "Shenandoah", "Haida", "Latvian",
                                       "Ceramics", "Mysterious Britain", "Island Stories",
                                       "Visions and Beliefs"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

Running beneath the collection's contemporary art and critical theory is a persistent attention to vernacular and indigenous cultural forms — traditions that exist outside institutional art worlds but possess their own rigor, beauty, and systems of transmission. The shape-note singing tradition is the clearest example: {format_book_ref(indices['by_title']['The Sacred Harp'])} (the foundational 1844 hymnal) alongside {format_book_ref(indices['by_title']['The Shenandoah Harmony'])} (a 2013 revival tunebook) document a communal music-making practice that has survived for over two centuries by privileging participation over performance, community over virtuosity.

The indigenous literary traditions are represented with unusual depth. Robert Bringhurst's {format_book_ref(indices['by_title']['A Story as Sharp as a Knife: The Classical Haida Mythtellers and Their World'])} and the companion {format_book_ref(indices['by_title']['Being in Being'])} present Haida oral literature as a body of classical art comparable to Homer or the Norse sagas — the latter also present via {format_book_ref(indices['by_title']['Norse Mythology'])} and {format_book_ref(indices['by_title']["Njal's Saga"])}. Irish folklore appears through {format_book_ref(indices['by_title']['Visions and Beliefs'])} by Lady Gregory and {format_book_ref(indices['by_title']['Island Stories: Tales and Legends from the West'])}. The British folk tradition surfaces in {format_book_ref(indices['by_title']['Mysterious Britain'])}, which documents pagan survivals and folk customs through Homer Sykes's documentary photography.

The craft traditions form another branch: {format_book_ref(indices['by_title']['Knit Like a Latvian'])} preserves pattern traditions from Baltic textile culture, {format_book_ref(indices['by_title']['Ceramics Bible'])} documents studio ceramics as a living craft, and {format_book_ref(indices['by_title']['Books, Boxes & Portfolios'])} treats bookbinding as a material practice. These aren't antiquarian interests — they connect to the collection's broader argument (implicit across many holdings) that handmade, embodied, community-based cultural forms offer something that institutional art and digital media cannot replace. This thread connects to [Sculpture, Installation, and Materiality](sculpture-installation-and-materiality.md) and to the environmental thinking in [Ecology, Land, and the Nature Tradition](ecology-land-and-the-nature-tradition.md).

See also: [Sound, Listening, and Experimental Music](sound-listening-and-experimental-music.md), [Myth, Spirituality, and the Sacred](myth-spirituality-and-the-sacred.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_sound(catalog, indices):
    title = "Sound, Listening, and Experimental Music"
    books = find_books(catalog, indices,
                       themes=["experimental music", "sound", "jazz", "improvisation",
                               "sound art", "sound studies", "music philosophy",
                               "listening", "acoustic ecology", "deep listening"],
                       title_keywords=["Soundscape", "Arcana", "Musician", "Voice in the Headphones",
                                       "Soloists", "Ken Burns", "Coltrane", "Oliveros",
                                       "New Directions", "Records Ruin"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The collection's music holdings cluster around two poles: the theoretical investigation of sound as a medium, and the documentation of experimental and improvised music practices. {format_book_ref(indices['by_title']['The Soundscape'])} by R. Murray Schafer provides the conceptual foundation — acoustic ecology as a way of attending to the sonic environment that parallels visual art's attention to seeing. {format_book_ref(indices['by_title']['The Voice in the Headphones'])} by David Grubbs extends this into questions about recording, mediation, and the phenomenology of listening, while {format_book_ref(indices['by_title']['The Musician as Philosopher'])} argues that experimental music constitutes genuine philosophical inquiry.

The practice-oriented texts include {format_book_ref(indices['by_title']['Arcana'])}, John Zorn's anthology of musicians writing about their own methods, and {format_book_ref(indices['by_title']['Software for People'])} by Pauline Oliveros, whose Deep Listening practice bridges music, meditation, and consciousness. {format_book_ref(indices['by_title']['Simultaneous Soloists'])} documents the collaboration between Anthony McCall and David Grubbs at Pioneer Works, connecting sound practice to the light-based installation tradition. Jazz appears through {format_book_ref(indices['by_title']['Ken Burns Jazz'])} and, more obliquely, through {format_book_ref(indices['by_title']['Monument Eternal'])}, the Alice Coltrane exhibition catalog that positions sonic innovation within spiritual practice.

These holdings connect to multiple other threads: the Fluxus tradition of sound scores and intermedia events ([Fluxus and Neo-Dada](fluxus-and-neo-dada.md)); the video art emphasis on the audiovisual relationship ([Video Art and Media Theory](video-art-and-media-theory.md)); and the vernacular musical traditions documented in the shape-note holdings ([Vernacular Cultural Forms](vernacular-cultural-forms.md)). The collection implies a view of sound as a primary artistic medium, not secondary to the visual — a position reinforced by the crossover figures like Paik, Anderson ({format_book_ref(indices['by_title']['United States'])}), and the recorded music thread in {format_book_ref(indices['by_title']['Records Ruin the Landscape'])}.

See also: [Vernacular Cultural Forms](vernacular-cultural-forms.md), [Video Art and Media Theory](video-art-and-media-theory.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_sculpture(catalog, indices):
    title = "Sculpture, Installation, and Materiality"
    books = find_books(catalog, indices,
                       themes=["sculpture", "installation", "process art", "materials",
                               "wire sculpture", "Land Art", "kinetic art", "materiality",
                               "post-minimalism"],
                       title_keywords=["Eva Hesse", "Ruth Asawa", "Matta-Clark", "Maya Lin",
                                       "Henry Moore", "Richard Long", "Boltanski",
                                       "Nancy Graves", "Kienholz", "Rebecca Horn",
                                       "Niki de Saint Phalle"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The sculpture holdings span from modernist form to post-minimalist process to site-specific intervention, tracing how three-dimensional art practice has expanded to encompass nearly every material and spatial condition. {format_book_ref(indices['by_title']['Henry Moore'])} anchors the modernist tradition of sculptural form, while {format_book_ref(indices['by_title']['Eva Hesse'])} represents the radical material experiments of post-minimalism — latex, fiberglass, rope — that opened sculpture to entropy, body, and chance. {format_book_ref(indices['by_title']['Ruth Asawa: Through Line'])} recovers a figure whose wire sculptures and community practice were long marginalized by the New York mainstream, connecting craft tradition to fine art innovation.

The site-specific and architectural interventions form a strong cluster. {format_book_ref(indices['by_title']['Gordon Matta-Clark'])} documents the building cuts that turned architecture itself into sculptural material, while {format_book_ref(indices['by_title']['Maya Lin: Boundaries'])} traces the memorial and landscape practice that bridges sculpture, architecture, and environmental art. {format_book_ref(indices['by_title']['Richard Long: Mountains and Waters'])} represents Land Art's dissolution of sculpture into walking and landscape, and {format_book_ref(indices['by_title']['Christian Boltanski'])} brings installation into dialogue with memory, loss, and the Holocaust.

The materiality thread extends through {format_book_ref(indices['by_title']['Nancy Graves'])}, whose work drew on natural history and science, and {format_book_ref(indices['by_title']['Niki de Saint Phalle & Jean Tinguely'])}, whose kinetic and monumental works merged sculpture with spectacle and public participation. The conceptual dimension is reinforced by {format_book_ref(indices['by_title']['thingworld'])}, which brings object-oriented ontology into dialogue with contemporary art practice. This cluster connects to [Fluxus and Neo-Dada](fluxus-and-neo-dada.md) through shared interests in process and materiality, and to [Vernacular Cultural Forms](vernacular-cultural-forms.md) through the craft tradition's emphasis on material knowledge.

See also: [Painting and Abstraction](painting-and-abstraction.md), [Architecture and the Built Environment](architecture-and-the-built-environment.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_conceptual(catalog, indices):
    title = "Conceptual and Rule-Based Art"
    books = find_books(catalog, indices,
                       themes=["conceptual art", "rule-based art", "algorithmic art",
                               "generative art", "instruction art", "text-based art",
                               "dematerialization"],
                       title_keywords=["Logical Conclusions", "Mechanism of Meaning",
                                       "Sophie Calle", "Glenn Ligon", "David Diao",
                                       "Adrian Piper", "Conceptual"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The conceptual art holdings are inflected toward two related but distinct practices: rule-based systems that generate art through predetermined procedures, and text-based work that uses language as primary medium. {format_book_ref(indices['by_title']['Logical Conclusions: 40 Years of Rule-Based Art'])} surveys four decades of algorithmic and systems-based art, from Sol LeWitt's wall drawings to contemporary generative practices — a lineage that runs directly into the digital art and creative coding territory documented in [Digital Art and Blockchain Culture](digital-art-and-blockchain-culture.md). {format_book_ref(indices['by_title']['The Mechanism of Meaning'])} by Arakawa and Madeline Gins represents the most philosophically ambitious strand: art as a mechanism for investigating perception and cognition.

The text-based branch includes several major figures. {format_book_ref(indices['by_title']['Glenn Ligon — Some Changes'])} documents an artist whose stenciled text paintings collapse conceptual art, African American literary tradition, and identity politics into a single practice. {format_book_ref(indices['by_title']['Sophie Calle'])} represents the autobiographical-conceptual tradition where personal narrative becomes systematic investigation. {format_book_ref(indices['by_title']['David Diao'])} occupies a unique position: a painter whose conceptual approach interrogates the history and mythology of modernism itself. {format_book_ref(indices['by_title']['Adrian Piper: A Reader'])} connects conceptual practice to questions of race, performance, and institutional critique.

The instruction-based thread links conceptual art back to [Fluxus and Neo-Dada](fluxus-and-neo-dada.md) (Ono's {format_book_ref(indices['by_title']['Grapefruit'])}) and forward to computational art ({format_book_ref(indices['by_title']['Processing'])}). All share a fundamental premise: that art can be defined as a set of instructions or rules, with execution as a secondary operation. This is arguably the deepest structural connection in the collection — the thread that ties Fluxus scores to database cinema to blockchain-based generative art.

See also: [Digital Art and Blockchain Culture](digital-art-and-blockchain-culture.md), [Painting and Abstraction](painting-and-abstraction.md), [Fluxus and Neo-Dada](fluxus-and-neo-dada.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_photography(catalog, indices):
    title = "Photography and the Documentary Image"
    books = find_books(catalog, indices,
                       themes=["photography", "documentary", "photojournalism",
                               "street photography", "portraiture", "women photographers"],
                       title_keywords=["Naked City", "Dirty Windows", "Hidden Mother",
                                       "Mapplethorpe", "Ansel Adams", "Larry Burrows",
                                       "Chris Verene", "Atlas", "Women Photographers"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The photography holdings reveal an interest in the medium's documentary and social functions rather than purely formal concerns. {format_book_ref(indices['by_title']['Naked City'])} by Weegee establishes the raw, tabloid tradition of urban photography, while {format_book_ref(indices['by_title']['Dirty Windows'])} by Merry Alpern extends this into voyeuristic surveillance — both reflecting on the ethics of looking. {format_book_ref(indices['by_title']['Hidden Mother'])} by Laura Larson examines Victorian-era portrait conventions to expose hidden labor and gendered erasure, connecting photography to feminist critique.

The collection balances the documentary tradition with more expansive uses of the medium. {format_book_ref(indices['by_title']['Ansel Adams: An Autobiography'])} represents landscape photography's intersection with environmental consciousness (linking to [Ecology, Land, and the Nature Tradition](ecology-land-and-the-nature-tradition.md)), while {format_book_ref(indices['by_title']['Larry Burrows Vietnam'])} documents photojournalism's confrontation with war. {format_book_ref(indices['by_title']['Sophie Calle'])} uses photography as a conceptual tool for investigating intimacy and surveillance, and {format_book_ref(indices['by_title']['Aziz + Cucher'])} pushes photography into digital manipulation and posthuman territory. {format_book_ref(indices['by_title']['A History of Women Photographers'])} provides the historical recovery narrative.

The Richter connection is significant: {format_book_ref(indices['by_title']['Atlas'])} documents Gerhard Richter's photographic archive — the raw material that feeds his painting practice — establishing a bridge between photography and [Painting and Abstraction](painting-and-abstraction.md). Similarly, Hollis Frampton's movement from photography to structural film ({format_book_ref(indices['by_title']['Circles of Confusion'])}) links this cluster to [Film Theory and the Cinematic Image](film-theory-and-the-cinematic-image.md). Photography in this collection is never purely about the photograph — it's always connected to questions of power, gender, technology, and the relationship between seeing and knowing.

See also: [Feminism, Gender, and Identity](feminism-gender-and-identity.md), [Film Theory and the Cinematic Image](film-theory-and-the-cinematic-image.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_political(catalog, indices):
    title = "Political Philosophy and Radical Thought"
    books = find_books(catalog, indices,
                       themes=["anarchism", "political philosophy", "political theory",
                               "radical politics", "anti-capitalism", "direct action",
                               "capitalism", "resistance", "political economy",
                               "globalization"],
                       title_keywords=["Caliban", "Debt", "Empire", "Multitude",
                                       "Achieving Our Country", "Art of Not Being Governed",
                                       "Discovery of Freedom", "New Jim Crow", "Antifa",
                                       "Accumulation", "Anarchism"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The political philosophy holdings span from anarchist theory to liberal pragmatism, but the center of gravity lies in radical critique. David Graeber appears three times ({format_book_ref(indices['by_title']['Debt: The First 5,000 Years'])}, {format_book_ref(indices['by_title']['Direct Action: An Ethnography'])}, {format_book_ref(indices['by_title']['Possibilities'])}), establishing a strong anarchist-anthropological strand. Hardt and Negri's {format_book_ref(indices['by_title']['Empire'])} and {format_book_ref(indices['by_title']['Multitude'])} represent the post-Marxist analysis of globalization, while {format_book_ref(indices['by_title']['Caliban and the Witch'])} by Silvia Federici reframes the history of primitive accumulation through feminist and bodily politics.

The American political thread runs from {format_book_ref(indices['by_title']['Achieving Our Country'])} by Richard Rorty (the pragmatist case for patriotic leftism) through {format_book_ref(indices['by_title']['The New Jim Crow'])} by Michelle Alexander (mass incarceration as the new racial caste system) to {format_book_ref(indices['by_title']['Detroit: I Do Mind Dying'])} (Black radical labor organizing in the auto industry). These aren't purely theoretical — they connect to the social practice art holdings ({format_book_ref(indices['by_title']['Living as Form'])}, {format_book_ref(indices['by_title']['What We Want Is Free'])}) where political organizing and artistic practice converge.

The anarchist/libertarian tradition is represented across a surprising range: {format_book_ref(indices['by_title']['Anarchism'])} by Guérin, {format_book_ref(indices['by_title']['The Art of Not Being Governed'])} by James C. Scott, and {format_book_ref(indices['by_title']['The Discovery of Freedom'])} by Rose Wilder Lane — the latter an unusual inclusion that suggests an interest in freedom as a concept that crosses the left-right divide. The technology-critique wing connects to [Ecology, Land, and the Nature Tradition](ecology-land-and-the-nature-tradition.md) through anti-civilization thinkers, while the economic theory strand ({format_book_ref(indices['by_title']['The Wealth of Nations'])}, {format_book_ref(indices['by_title']['Critique of Commodity Aesthetics'])}) links to [Situationism, Spectacle, and Everyday Life](situationism-spectacle-and-everyday-life.md).

See also: [Situationism, Spectacle, and Everyday Life](situationism-spectacle-and-everyday-life.md), [Feminism, Gender, and Identity](feminism-gender-and-identity.md), [Counterculture and Radical Pedagogy](counterculture-and-radical-pedagogy.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_painting(catalog, indices):
    title = "Painting and Abstraction"
    books = find_books(catalog, indices,
                       themes=["painting", "abstraction", "abstract painting",
                               "Neo-Expressionism", "color theory"],
                       title_keywords=["Whitten", "Winters", "Richter", "Penck",
                                       "Bulatov", "Ninth Street Women", "Superflat",
                                       "Buffalo Heads", "Der Blaue Reiter", "Hilma af Klint"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The painting holdings reveal a specific taste: not painting as a settled tradition but painting as a site of conceptual investigation and material experiment. {format_book_ref(indices['by_title']['Jack Whitten: The Messenger'])} documents one of the most innovative painters of the postwar period, whose evolution from gestural abstraction to mosaic-like tile paintings represents painting as perpetual material research. {format_book_ref(indices['by_title']['Terry Winters'])} — the most-connected node in the entire catalog's relationship graph — occupies a pivotal position between biological form, systems thinking, and abstraction.

The German strand is strong: {format_book_ref(indices['by_title']['Gerhard Richter: Writings 1962-1993'])} provides the intellectual framework of an artist who made painting's relationship to photography and media its subject. {format_book_ref(indices['by_title']['A.R. Penck'])} brings Cold War semiotics and information theory into painting, while {format_book_ref(indices['by_title']['Erik Bulatov'])} represents the Moscow Conceptualist approach to painting as ideological surface. {format_book_ref(indices['by_title']['Ninth Street Women'])} recovers the women of Abstract Expressionism — de Kooning, Krasner, Mitchell, Frankenthaler, Hartigan — from canonical erasure, connecting to [Feminism, Gender, and Identity](feminism-gender-and-identity.md).

The deeper history includes {format_book_ref(indices['by_title']['Der Blaue Reiter'])} and {format_book_ref(indices['by_title']['Hilma af Klint: Notes and Methods'])}, connecting early abstraction to spiritual and theosophical traditions — a lineage that runs through the collection's [Myth, Spirituality, and the Sacred](myth-spirituality-and-the-sacred.md) thread. {format_book_ref(indices['by_title']['David Diao'])} represents painting as meta-commentary on its own history, while {format_book_ref(indices['by_title']['Superflat'])} by Murakami brings Japanese pop culture into dialogue with Western art-historical categories. The collection treats painting not as a medium in crisis but as one continuously reinventing its terms.

See also: [Sculpture, Installation, and Materiality](sculpture-installation-and-materiality.md), [Art Criticism and the Philosophy of Art](art-criticism-and-the-philosophy-of-art.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_media_theory(catalog, indices):
    title = "Media Theory and Digital Culture"
    books = find_books(catalog, indices,
                       themes=["media theory", "digital culture", "media criticism",
                               "platform capitalism", "internet", "social media",
                               "technology critique", "cyberculture"],
                       title_keywords=["Protocol", "Social Media", "Body Invaders",
                                       "Electronic Culture", "Digital Delirium",
                                       "Amusing Ourselves", "Flusser", "Uncanny Networks",
                                       "Within the Context", "Against Platforms",
                                       "Imaginary Futures"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The media theory holdings form a critical genealogy running from pre-digital media criticism through internet theory to platform-era critique. {format_book_ref(indices['by_title']['Amusing Ourselves to Death'])} by Neil Postman and {format_book_ref(indices['by_title']['Within the Context of No Context'])} by George W.S. Trow establish the pre-internet baseline: television's transformation of public discourse into entertainment. From there, the collection traces the digital turn through {format_book_ref(indices['by_title']['Electronic Culture'])}, {format_book_ref(indices['by_title']['Body Invaders'])}, and {format_book_ref(indices['by_title']['Digital Delirium'])} — the Kroker-edited volumes that mapped postmodern technoculture in the 1990s.

The internet-native theory appears in {format_book_ref(indices['by_title']['Protocol'])} by Alexander Galloway, which reads internet architecture through Deleuze's theory of control societies, and {format_book_ref(indices['by_title']['The Social Media Reader'])}, which documents the participatory culture turn. {format_book_ref(indices['by_title']['Uncanny Networks'])} by Geert Lovink offers the net criticism perspective, while {format_book_ref(indices['by_title']['Imaginary Futures'])} historicizes digital utopianism as ideology. {format_book_ref(indices['by_title']['Writings'])} by Vilém Flusser provides a uniquely prescient philosophy of technical images and post-history that anticipated many of digital culture's epistemological challenges.

The contemporary critique strand includes {format_book_ref(indices['by_title']['Against Platforms'])} by Mike Pepi, {format_book_ref(indices['by_title']['Art in the After-Culture'])} by Ben Davis (which connects platform capitalism to the art world), and the Mark Fisher works ({format_book_ref(indices['by_title']['Postcapitalist Desire'])}, {format_book_ref(indices['by_title']['The Weird and the Eerie'])}) that analyze cultural production under capitalist realism. The overall arc of these holdings traces how each new media technology provokes fresh forms of both artistic practice and critical analysis — a pattern central to [Digital Art and Blockchain Culture](digital-art-and-blockchain-culture.md) and [Video Art and Media Theory](video-art-and-media-theory.md).

See also: [Situationism, Spectacle, and Everyday Life](situationism-spectacle-and-everyday-life.md), [Digital Art and Blockchain Culture](digital-art-and-blockchain-culture.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_film(catalog, indices):
    title = "Film Theory and the Cinematic Image"
    books = find_books(catalog, indices,
                       themes=["cinema", "film theory", "experimental film", "film studies",
                               "French New Wave", "film modernism", "structural film"],
                       title_keywords=["Godard", "Frampton", "Marker", "Lynch", "La Jetée",
                                       "Film Art", "Circles of Confusion", "Cinema 2",
                                       "Werner Herzog", "Film Blackness"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The film holdings cluster around auteur cinema, experimental film, and film theory rather than mainstream film studies. Godard dominates the auteur section with three titles: {format_book_ref(indices['by_title']['Godard on Godard'])}, {format_book_ref(indices['by_title']['Forever Godard'])}, and {format_book_ref(indices['by_title']['Jean-Luc Godard: Son+Image'])} — documenting the filmmaker who most radically collapsed the boundary between cinema practice and critical theory. Chris Marker appears through {format_book_ref(indices['by_title']['Chris Marker'])} and {format_book_ref(indices['by_title']['La Jetée'])}, representing the essay film tradition that treats cinema as a medium for philosophical investigation of memory and time.

The experimental film branch is anchored by {format_book_ref(indices['by_title']['Hollis Frampton: Navigating the Infinite Cinema'])}, which positions Frampton as a bridge between minimalist art, conceptual photography, and structural film, and {format_book_ref(indices['by_title']['Circles of Confusion'])}, Frampton's own critical writings. {format_book_ref(indices['by_title']['Film Art'])} by Bordwell and Thompson provides the analytical toolkit, while Deleuze's {format_book_ref(indices['by_title']['Cinema 2: The Time-Image'])} offers the philosophical framework — the concept of the "time-image" that has influenced generations of video and moving image artists.

{format_book_ref(indices['by_title']['Film Blackness'])} by Michael Boyce Gillespie brings questions of race and aesthetics into film theory, while {format_book_ref(indices['by_title']['Werner Herzog: A Guide for the Perplexed'])} represents the documentary tradition where cinema becomes a vehicle for what Herzog calls "ecstatic truth." The {format_book_ref(indices['by_title']['David Lynch'])} monograph focuses on Lynch's painting and visual art rather than his films, complicating the boundary between cinema and visual art that the collection consistently refuses to respect. This thread connects to [Video Art and Media Theory](video-art-and-media-theory.md) — the two clusters share many artists (Frampton, Marker, the essay film tradition) who work across both media.

See also: [Video Art and Media Theory](video-art-and-media-theory.md), [French Theory in the American Art World](french-theory-in-the-american-art-world.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_feminism(catalog, indices):
    title = "Feminism, Gender, and Identity"
    books = find_books(catalog, indices,
                       themes=["feminism", "women artists", "feminist art",
                               "gender", "women writers", "identity politics",
                               "feminist theory", "xenofeminism", "posthumanism"],
                       title_keywords=["Room of One's Own", "Xenofeminism", "Ninth Street Women",
                                       "Woman Destroyed", "Caliban", "When Species Meet",
                                       "Women Photographers", "Hidden Mother", "Beauvoir",
                                       "In the Company of Women"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

Feminist thought runs through the collection not as a separate category but as a critical lens applied across multiple domains. The foundational texts include {format_book_ref(indices['by_title']["A Room of One's Own"])} by Virginia Woolf, {format_book_ref(indices['by_title']['The Woman Destroyed'])} by Simone de Beauvoir, and {format_book_ref(indices['by_title']['Caliban and the Witch'])} by Silvia Federici — spanning liberal feminism's demand for creative autonomy, existentialist feminism's analysis of self-deception, and Marxist-feminist history of the body and primitive accumulation. {format_book_ref(indices['by_title']['Xenofeminism'])} by Helen Hester brings the thread into the contemporary moment with its anti-naturalist, technology-embracing political theory.

In art history, the collection makes a sustained case for recovering women's contributions. {format_book_ref(indices['by_title']['Ninth Street Women'])} is the landmark account of five women Abstract Expressionists written out of the canonical narrative. {format_book_ref(indices['by_title']['A History of Women Photographers'])} performs a similar recovery for photography. Individual women artists receive serious attention: {format_book_ref(indices['by_title']['Eva Hesse'])}, {format_book_ref(indices['by_title']['Ruth Asawa: Through Line'])}, {format_book_ref(indices['by_title']['Hilma af Klint: Notes and Methods'])}, {format_book_ref(indices['by_title']['Anni Albers'])}, {format_book_ref(indices['by_title']['Sophie Calle'])}, {format_book_ref(indices['by_title']['Joan Jonas: Good Night Good Morning'])} — across sculpture, textiles, conceptual art, video, and abstraction.

The posthumanist wing extends feminist thought into questions of species, technology, and embodiment. Donna Haraway's {format_book_ref(indices['by_title']['When Species Meet'])} and Rosi Braidotti's {format_book_ref(indices['by_title']['The Posthuman'])} connect to the digital body themes in {format_book_ref(indices['by_title']['Aziz + Cucher'])} and {format_book_ref(indices['by_title']['Body Invaders'])}. The literary dimension includes Woolf's novels ({format_book_ref(indices['by_title']['Mrs Dalloway'])}, {format_book_ref(indices['by_title']['Orlando'])}), confessional poetry ({format_book_ref(indices['by_title']['Anne Sexton'])}), and Atwood's verse ({format_book_ref(indices['by_title']['Selected Poems'])}). The collection suggests that feminism is not a subject position but a methodology — applicable to art, economics, technology, and ecology alike.

See also: [Political Philosophy and Radical Thought](political-philosophy-and-radical-thought.md), [Painting and Abstraction](painting-and-abstraction.md), [Existentialism and European Literary Voices](existentialism-and-european-literary-voices.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_ecology(catalog, indices):
    title = "Ecology, Land, and the Nature Tradition"
    books = find_books(catalog, indices,
                       themes=["environmentalism", "ecology", "nature", "wilderness",
                               "landscape", "sustainability", "bioregionalism",
                               "nature writing", "agrarianism"],
                       title_keywords=["Wilderness", "Against the Machine", "This Land",
                                       "Low Tech", "Continuous Harmony", "Gary Snyder",
                                       "No Nature", "Thoreau", "Ministry for the Future",
                                       "Derrick Jensen", "Meat", "Off the Grid",
                                       "Metamorphosis of Plants"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The environmental holdings range from deep ecology to practical sustainability, but their intellectual center is the question of how humans relate to the non-human world. {format_book_ref(indices['by_title']['Wilderness and the American Mind'])} by Roderick Nash provides the intellectual history of wilderness as a concept, while Gary Snyder's {format_book_ref(indices['by_title']['No Nature'])} and {format_book_ref(indices['by_title']['The Gary Snyder Reader'])} bring Buddhist ecological thought into the nature writing tradition. Wendell Berry's {format_book_ref(indices['by_title']['A Continuous Harmony'])} argues for agrarian practice as both ecological and moral commitment, and {format_book_ref(indices['by_title']['Through the Year with Thoreau'])} anchors the transcendentalist root of American nature thought.

The technology-critical wing is particularly sharp. {format_book_ref(indices['by_title']['Against the Machine'])} by Paul Kingsnorth articulates eco-pessimism and post-environmentalism, {format_book_ref(indices['by_title']['In the Absence of the Sacred'])} by Jerry Mander connects technology critique to indigenous rights, and {format_book_ref(indices['by_title']['The Derrick Jensen Reader'])} represents the radical ecology that questions civilization itself. {format_book_ref(indices['by_title']['Technological Slavery'])} is the most extreme position in the collection — anti-civilization thought pushed to its logical endpoint. Against these, {format_book_ref(indices['by_title']['The Ministry for the Future'])} by Kim Stanley Robinson imagines pragmatic political solutions to climate crisis, and {format_book_ref(indices['by_title']['The Low Tech Magazine'])} advocates for appropriate technology rather than technological refusal.

The visual art connections are significant: {format_book_ref(indices['by_title']['This Land'])} by David Opdyke and Lawrence Weschler brings collage and environmental art together, {format_book_ref(indices['by_title']['Richard Long: Mountains and Waters'])} represents Land Art's direct engagement with landscape, and {format_book_ref(indices['by_title']['Ansel Adams: An Autobiography'])} connects landscape photography to the conservation movement. The ecological thread also runs through the [Vernacular Cultural Forms](vernacular-cultural-forms.md) holdings, where traditional practices embody sustainable relationships with materials and land.

See also: [Vernacular Cultural Forms](vernacular-cultural-forms.md), [Political Philosophy and Radical Thought](political-philosophy-and-radical-thought.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_american_lit(catalog, indices):
    title = "American Literary Traditions"
    books = find_books(catalog, indices,
                       themes=["American literature", "short fiction", "confessional poetry",
                               "minimalism", "satire", "Southern Gothic"],
                       title_keywords=["Twain", "Saunders", "Carver", "Faulkner", "Lowell",
                                       "Dickinson", "Century of Fiction", "Huckleberry",
                                       "Book of Delights", "Sellout", "Chabon"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The American literature holdings center on two modes: the minimalist short story tradition and the satirical novel. Raymond Carver appears twice — {format_book_ref(indices['by_title']['Carver: Collected Stories'])} and {format_book_ref(indices['by_title']['Fires: Essays, Poems, Stories'])} — representing the stripped-down, working-class realism that defined late-20th-century American fiction. George Saunders's {format_book_ref(indices['by_title']['In Persuasion Nation'])} extends this tradition into absurdist satire of consumer culture, while {format_book_ref(indices['by_title']['The Sellout'])} by Paul Beatty pushes racial satire to its limits. {format_book_ref(indices['by_title']['A Century of Fiction in The New Yorker 1925–2025'])} provides the institutional frame — the magazine as arbiter of American literary taste for a century.

The older canon is selectively present. {format_book_ref(indices['by_title']['Adventures of Huckleberry Finn'])} represents Twain's vernacular revolution, {format_book_ref(indices['by_title']['The Mansion'])} is Faulkner's late Yoknapatawpha work on class and revenge, and {format_book_ref(indices['by_title']['Emily Dickinson: The Gorgeous Nothings'])} reframes Dickinson as a visual artist working at the boundary of text and image — connecting her to the conceptual art interests in [Conceptual and Rule-Based Art](conceptual-and-rule-based-art.md). The confessional poets ({format_book_ref(indices['by_title']['Life Studies / For the Union Dead'])} by Lowell, {format_book_ref(indices['by_title']['Anne Sexton'])}) represent the mid-century tradition of turning private suffering into public art.

The postmodern and contemporary strand includes Pynchon's {format_book_ref(indices['by_title']['Vineland'])}, which connects counterculture nostalgia to surveillance paranoia, and {format_book_ref(indices['by_title']['The Nix'])} by Nathan Hill, which maps generational conflict through the lens of digital culture. The essay tradition appears through {format_book_ref(indices['by_title']['The Book of Delights'])} by Ross Gay and {format_book_ref(indices['by_title']['Manhood for Amateurs'])} by Michael Chabon — more personal and lyrical modes that complement the fiction holdings. The broader American literary landscape connects to [Beat Literature and the Burroughs Corpus](beat-literature-and-the-burroughs-corpus.md) and to the race and identity themes in [Feminism, Gender, and Identity](feminism-gender-and-identity.md).

See also: [Beat Literature and the Burroughs Corpus](beat-literature-and-the-burroughs-corpus.md), [Existentialism and European Literary Voices](existentialism-and-european-literary-voices.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_european_lit(catalog, indices):
    title = "Existentialism and European Literary Voices"
    books = find_books(catalog, indices,
                       themes=["existentialism", "Czech literature", "French literature",
                               "German literature", "Italian literature", "modernism",
                               "Victorian literature"],
                       title_keywords=["Woolf", "Kundera", "Brontë", "Celan", "Rilke",
                                       "Pavese", "Coetzee", "Kazantzakis", "Erpenbeck",
                                       "Kafka", "Camus", "Genet", "Dinesen", "Ditlevsen",
                                       "Ferrante", "Houellebecq", "Grass"])
    core = [b for b, s in books[:15]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The European literary holdings cluster around existentialist and modernist traditions, with particular depth in French and German-language writing. Camus appears in both his philosophical ({format_book_ref(indices['by_title']["L'Étranger"])}) and lyrical ({format_book_ref(indices['by_title']["Noces suivi de L'Été"])}) modes, while Kafka's {format_book_ref(indices['by_title']['The Trial'])} represents the absurdist branch that influenced the Theater of the Absurd holdings ({format_book_ref(indices['by_title']['Ionesco'])}, {format_book_ref(indices['by_title']['Kaspar and Other Plays'])}). Virginia Woolf's {format_book_ref(indices['by_title']['Mrs Dalloway'])} and {format_book_ref(indices['by_title']['Orlando'])} embody the modernist stream-of-consciousness tradition, while Emily Brontë's {format_book_ref(indices['by_title']['Wuthering Heights'])} anchors the Victorian gothic.

The poetry holdings are concentrated and potent. Paul Celan ({format_book_ref(indices['by_title']['Poems of Paul Celan'])}) represents the post-Holocaust attempt to make language speak from the ruins, while Rilke connects to the tradition of poetic interiority and transformation. Cesare Pavese's {format_book_ref(indices['by_title']['Hard-Labor'])} brings Italian political exile into the picture, and Kenneth Rexroth's translations ({format_book_ref(indices['by_title']['One Hundred Poems from the Chinese'])}, {format_book_ref(indices['by_title']['The Orchid Boat'])}) bridge Western and East Asian literary traditions.

The contemporary strand includes {format_book_ref(indices['by_title']['Heimsuchung'])} by Jenny Erpenbeck, which maps German history through a single piece of property, {format_book_ref(indices['by_title']['The Unbearable Lightness of Being'])} by Milan Kundera, and {format_book_ref(indices['by_title']['Disgrace'])} by J.M. Coetzee — post-apartheid South Africa refracting European literary tradition through colonial history. {format_book_ref(indices['by_title']['Those Who Leave and Those Who Stay'])} by Elena Ferrante brings female friendship and class to the Italian literary tradition. The women's literary tradition connects to [Feminism, Gender, and Identity](feminism-gender-and-identity.md), while the philosophical dimension links to [French Theory in the American Art World](french-theory-in-the-american-art-world.md).

See also: [French Theory in the American Art World](french-theory-in-the-american-art-world.md), [American Literary Traditions](american-literary-traditions.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_myth(catalog, indices):
    title = "Myth, Spirituality, and the Sacred"
    books = find_books(catalog, indices,
                       themes=["mythology", "spirituality", "religion", "sacred",
                               "theology", "mysticism", "Buddhism", "meditation",
                               "transgression", "monomyth"],
                       title_keywords=["Hero with a Thousand Faces", "Norse Mythology",
                                       "Meditation and the Bible", "Confessions",
                                       "Last Temptation", "Coltrane", "Become What You Are",
                                       "Theory of Religion", "Visions of Excess",
                                       "Mind in the Cave", "Visions and Beliefs"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The mythological and spiritual holdings form a cluster that connects ancient narrative structures to contemporary art practice and philosophical inquiry. Joseph Campbell's {format_book_ref(indices['by_title']['The Hero with a Thousand Faces'])} provides the comparative mythology framework, while {format_book_ref(indices['by_title']['Norse Mythology'])} by Neil Gaiman and {format_book_ref(indices['by_title']["Njal's Saga"])} offer primary and retold Norse material. {format_book_ref(indices['by_title']['The Mind in the Cave'])} pushes the investigation back to prehistoric art, arguing that shamanic consciousness shaped the earliest image-making — a deep connection to the collection's interest in altered states and visionary experience.

The religious texts span traditions: Augustine's {format_book_ref(indices['by_title']['Confessions'])} (the foundational Western autobiography of conversion), {format_book_ref(indices['by_title']['Meditation and the Bible'])} by Aryeh Kaplan (Jewish contemplative practice), {format_book_ref(indices['by_title']['Become What You Are'])} by Alan Watts (Zen Buddhism and Taoism), and Kazantzakis's {format_book_ref(indices['by_title']['The Last Temptation'])} (the sacred and the human in creative tension). Bataille's {format_book_ref(indices['by_title']['Theory of Religion'])} and {format_book_ref(indices['by_title']['Visions of Excess'])} approach the sacred through transgression — the sacred as what exceeds rational containment.

The art-practice connections are revealing: {format_book_ref(indices['by_title']['Monument Eternal'])} positions Alice Coltrane's music within spiritual practice, {format_book_ref(indices['by_title']['Hilma af Klint: Notes and Methods'])} documents abstraction's roots in spiritualism, and {format_book_ref(indices['by_title']['Bill Viola'])} represents video art's engagement with contemplative traditions. The collection treats the sacred not as a historical curiosity but as a living dimension of creative practice — connected to [Sound, Listening, and Experimental Music](sound-listening-and-experimental-music.md) through sonic spirituality and to [Vernacular Cultural Forms](vernacular-cultural-forms.md) through sacred singing traditions.

See also: [Vernacular Cultural Forms](vernacular-cultural-forms.md), [Sound, Listening, and Experimental Music](sound-listening-and-experimental-music.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_art_criticism(catalog, indices):
    title = "Art Criticism and the Philosophy of Art"
    books = find_books(catalog, indices,
                       themes=["art criticism", "philosophy of art", "aesthetics",
                               "art world", "art market", "art institutions", "beauty"],
                       title_keywords=["Invisible Dragon", "Transfiguration", "Perpetual Inventory",
                                       "Philosophical Skepticism", "Best Art", "I Like Your Work",
                                       "Art School", "Inside the Studio", "Art Spirit",
                                       "Ways of Seeing", "Art in the After-Culture"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The art criticism holdings map the field from analytical philosophy through polemic to institutional sociology. Arthur Danto's {format_book_ref(indices['by_title']['The Transfiguration of the Commonplace'])} provides the philosophical foundation: the question of what makes something art when it is perceptually indistinguishable from a non-art object. Dave Hickey's {format_book_ref(indices['by_title']['The Invisible Dragon'])} counters with a passionate defense of beauty as democracy, while Rosalind Krauss's {format_book_ref(indices['by_title']['Perpetual Inventory'])} represents the October journal tradition of theoretically rigorous criticism. {format_book_ref(indices['by_title']['Philosophical Skepticism as the Subject of Art'])} by David Carrier extends the philosophical conversation by arguing that major artworks enact skeptical arguments about reality.

The institutional and sociological dimension includes {format_book_ref(indices['by_title']['The Best Art in the World'])}, which interrogates the power structures behind claims of artistic excellence, {format_book_ref(indices['by_title']['I Like Your Work: Art and Etiquette'])}, a witty anatomy of MFA culture and professional practice, and {format_book_ref(indices['by_title']['Art School'])}, which examines the pedagogical infrastructure of contemporary art. {format_book_ref(indices['by_title']['Inside the Studio: Two Decades of Talks with Artists in New York'])} provides primary-source material — artists speaking in their own voices about practice.

John Berger's {format_book_ref(indices['by_title']['Ways of Seeing'])} bridges art criticism and cultural theory, connecting to the [Situationism, Spectacle, and Everyday Life](situationism-spectacle-and-everyday-life.md) thread through its analysis of visual ideology. {format_book_ref(indices['by_title']['Art in the After-Culture'])} by Ben Davis brings art criticism into the platform era, while {format_book_ref(indices['by_title']['The Art Spirit'])} by Robert Henri anchors the tradition in the democratic, experiential approach of the Ashcan School. The overall arc suggests a view of criticism not as external judgment but as a practice continuous with art-making itself.

See also: [Painting and Abstraction](painting-and-abstraction.md), [French Theory in the American Art World](french-theory-in-the-american-art-world.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_counterculture(catalog, indices):
    title = "Counterculture and Radical Pedagogy"
    books = find_books(catalog, indices,
                       themes=["counterculture", "radical pedagogy", "pedagogy",
                               "counter-education", "art education", "liberation"],
                       title_keywords=["Blueprint for Counter Education", "Teaching to Transgress",
                                       "What the Best College Teachers", "Art School",
                                       "Industrial Culture", "Re/Search"])
    core = [b for b, s in books[:10]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The collection contains a distinct thread connecting 1960s counterculture to radical pedagogy and institutional critique. {format_book_ref(indices['by_title']['Blueprint for Counter Education'])} by Maurice Stein and Larry Miller is the centerpiece — a visual manifesto for dismantling institutional education through interdisciplinary, experiential learning that anticipated many contemporary debates about art education. {format_book_ref(indices['by_title']['Teaching to Transgress'])} by bell hooks extends the radical pedagogical tradition through questions of race, gender, and liberatory practice, while {format_book_ref(indices['by_title']['What the Best College Teachers Do'])} by Ken Bain offers a more empirical but still reform-minded approach.

The countercultural documentation includes {format_book_ref(indices['by_title']['Industrial Culture Handbook'])} from the Re/Search series, which mapped the post-punk industrial music and performance underground, and the companion {format_book_ref(indices['by_title']['Re/Search: J.G. Ballard'])}. {format_book_ref(indices['by_title']['Videofreex'])} documents the pirate television movement as countercultural media practice, while {format_book_ref(indices['by_title']['Sing Backwards and Weep'])} by Mark Lanegan provides a firsthand account of the Seattle grunge counterculture. The pedagogical thread connects to {format_book_ref(indices['by_title']['Art School'])}, which examines how art education institutionalizes (or fails to institutionalize) creative practice.

These holdings link counterculture to institutional transformation: the question is always how alternative practices relate to the mainstream structures they critique. This connects to [Political Philosophy and Radical Thought](political-philosophy-and-radical-thought.md) through shared commitments to autonomy and horizontal organizing, and to [Beat Literature and the Burroughs Corpus](beat-literature-and-the-burroughs-corpus.md) through the countercultural literary tradition.

See also: [Political Philosophy and Radical Thought](political-philosophy-and-radical-thought.md), [Beat Literature and the Burroughs Corpus](beat-literature-and-the-burroughs-corpus.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_architecture(catalog, indices):
    title = "Architecture and the Built Environment"
    books = find_books(catalog, indices,
                       themes=["architecture", "urbanism", "urban history",
                               "sustainable architecture", "design-build"],
                       title_keywords=["Rural Studio", "Off the Grid", "City of Quartz",
                                       "Architecture: Form", "Maya Lin", "Matta-Clark",
                                       "Leaning Girl", "High-Rise"])
    core = [b for b, s in books[:10]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The architecture holdings favor social engagement and critical practice over formal design. {format_book_ref(indices['by_title']['Rural Studio'])} documents Auburn University's design-build program in rural Alabama, where architecture students create structures for underserved communities using recycled materials — connecting architecture to social practice. {format_book_ref(indices['by_title']['Off the Grid'])} by Lori Ryker explores sustainable, self-sufficient building, while {format_book_ref(indices['by_title']['Architecture: Form, Space and Order'])} by Francis D.K. Ching provides the foundational design vocabulary.

The critical urbanism thread includes {format_book_ref(indices['by_title']['City of Quartz'])} by Mike Davis, a landmark analysis of Los Angeles as a city shaped by real estate, policing, and racial capitalism, and {format_book_ref(indices['by_title']['All That Is Solid Melts into Air'])} by Marshall Berman, which reads urban experience as the paradigmatic experience of modernity. Gordon Matta-Clark's building cuts ({format_book_ref(indices['by_title']['Gordon Matta-Clark'])}) treat architecture as material for sculptural intervention, while {format_book_ref(indices['by_title']['Maya Lin: Boundaries'])} bridges architecture, memorial, and landscape. {format_book_ref(indices['by_title']['The Leaning Girl'])} by Schuiten and Peeters imagines architecture as speculative fiction.

These holdings connect to [Sculpture, Installation, and Materiality](sculpture-installation-and-materiality.md) through the spatial and material overlap between architecture and installation art, and to [Ecology, Land, and the Nature Tradition](ecology-land-and-the-nature-tradition.md) through sustainable building practices. The social practice dimension links directly to [Political Philosophy and Radical Thought](political-philosophy-and-radical-thought.md) through questions about who architecture serves and how built environments encode power.

See also: [Sculpture, Installation, and Materiality](sculpture-installation-and-materiality.md), [Ecology, Land, and the Nature Tradition](ecology-land-and-the-nature-tradition.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_speculative(catalog, indices):
    title = "Science Fiction and Speculative Imagination"
    books = find_books(catalog, indices,
                       themes=["science fiction", "cyberpunk", "dystopia",
                               "cosmic horror", "speculative fiction", "weird fiction"],
                       title_keywords=["Ubik", "Software", "Lovecraft", "St. Clair",
                                       "Ministry for the Future", "Ballard", "Snow Crash",
                                       "Crystal Express", "Solaris", "Transmigration",
                                       "Sterling", "Atrocity Exhibition"])
    core = [b for b, s in books[:12]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The science fiction holdings cluster around three nodes: Philip K. Dick, J.G. Ballard, and the cyberpunk tradition, each representing distinct modes of speculative imagination. Dick appears through {format_book_ref(indices['by_title']['Ubik'])} and {format_book_ref(indices['by_title']['The Transmigration of Timothy Archer'])} — the paranoid ontology of reality breakdown and the late spiritual turn, respectively. Ballard is present through {format_book_ref(indices['by_title']['The Atrocity Exhibition'])}, {format_book_ref(indices['by_title']['High-Rise'])}, and {format_book_ref(indices['by_title']['Hello America'])}, plus the Re/Search interview volume — collectively mapping his vision of "inner space" as science fiction's true frontier. {format_book_ref(indices['by_title']['Re/Search: J.G. Ballard'])} from the Re/Search series provides the interview and critical apparatus.

The cyberpunk strand includes {format_book_ref(indices['by_title']['Snow Crash'])} by Neal Stephenson, {format_book_ref(indices['by_title']['Crystal Express'])} by Bruce Sterling, and {format_book_ref(indices['by_title']['Software'])} by Rudy Rucker — the three core voices of the movement that imagined the digital future now being built. These connect to [Digital Art and Blockchain Culture](digital-art-and-blockchain-culture.md) through shared concerns about virtual worlds, corporate control, and the nature of consciousness in digital systems. {format_book_ref(indices['by_title']['Solaris'])} by Stanisław Lem represents the European philosophical SF tradition — alien contact as epistemological limit.

H.P. Lovecraft appears through three titles ({format_book_ref(indices['by_title']['H.P. Lovecraft: At the Mountains of Madness'])}, {format_book_ref(indices['by_title']['The Lurking Fear'])}, {format_book_ref(indices['by_title']['The Dream-Quest of Unknown Kadath'])}), connecting to the cosmic horror tradition that Mark Fisher later theorized in {format_book_ref(indices['by_title']['The Weird and the Eerie'])}. {format_book_ref(indices['by_title']['The Best of Margaret St. Clair'])} recovers a forgotten feminist SF voice. {format_book_ref(indices['by_title']['The Ministry for the Future'])} by Kim Stanley Robinson represents the pragmatic-political wing of SF that imagines solutions rather than catastrophes — linking to [Ecology, Land, and the Nature Tradition](ecology-land-and-the-nature-tradition.md).

See also: [Media Theory and Digital Culture](media-theory-and-digital-culture.md), [Ecology, Land, and the Nature Tradition](ecology-land-and-the-nature-tradition.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


@wiki_page
def page_typography(catalog, indices):
    title = "Typography, Design, and Visual Language"
    books = find_books(catalog, indices,
                       themes=["typography", "graphic design", "design", "visual culture",
                               "book arts", "bookbinding"],
                       title_keywords=["Typographic Style", "Tibor Kalman", "2nd Sight",
                                       "Graphic Design", "Design Literacy", "Snap to Grid",
                                       "Books, Boxes", "Bringhurst"])
    core = [b for b, s in books[:10]]
    refs = "\n".join(f"- {format_book_ref(b)}" for b in core)

    content = f"""# {title}

The design holdings are practical rather than merely historical, centered on the tools and principles of typographic and graphic practice. {format_book_ref(indices['by_title']['The Elements of Typographic Style'])} by Robert Bringhurst is the canonical reference — a book that treats typography as both craft and cultural expression. It connects to the Bringhurst who also appears as translator of Haida literature ({format_book_ref(indices['by_title']['A Story as Sharp as a Knife: The Classical Haida Mythtellers and Their World'])}), a double role that embodies the collection's insistence on the continuity between refined formal practice and deep cultural knowledge.

{format_book_ref(indices['by_title']['Tibor Kalman: Perverse Optimist'])} represents design as cultural activism — Kalman's work at M&Co and Colors magazine pushed graphic design toward social engagement and political commentary. {format_book_ref(indices['by_title']['2nd Sight'])} by David Carson represents the deconstructivist counterpoint, while {format_book_ref(indices['by_title']['Graphic Design in the Mechanical Age'])} provides the historical genealogy from Constructivism and Bauhaus through to mid-century modernism. {format_book_ref(indices['by_title']['Design Literacy'])} and {format_book_ref(indices['by_title']['Graphic Design History'])} fill out the critical framework.

The book arts dimension — {format_book_ref(indices['by_title']['Books, Boxes & Portfolios'])} on bookbinding, {format_book_ref(indices['by_title']['Snap to Grid'])} on systems design — connects to [Vernacular Cultural Forms](vernacular-cultural-forms.md) through craft practice and to the artist's book tradition represented by Dieter Roth and Yoko Ono in [Fluxus and Neo-Dada](fluxus-and-neo-dada.md). Typography and design are positioned not as service disciplines but as cultural practices with their own intellectual traditions and critical histories.

See also: [Vernacular Cultural Forms](vernacular-cultural-forms.md), [Fluxus and Neo-Dada](fluxus-and-neo-dada.md)

## Key Titles

{refs}
"""
    return title, slug(title) + ".md", content


# ---------------------------------------------------------------------------
# INDEX generation
# ---------------------------------------------------------------------------

def generate_index(pages: list[tuple[str, str, str]]) -> str:
    """Generate INDEX.md linking all wiki pages."""
    lines = [
        "# Wiki Index",
        "",
        "Synthesized thematic pages tracing intellectual threads across the library.",
        "Each page synthesizes across multiple books rather than documenting individual titles.",
        "",
        "Generated from `catalog.json` by `scripts/generate_wiki.py`.",
        "",
        "---",
        "",
    ]

    # Extract one-line description from each page (first paragraph, truncated)
    for title, filename, content in sorted(pages, key=lambda x: x[0]):
        # Get first real paragraph after the title
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()
                       and not p.strip().startswith("#")
                       and not p.strip().startswith("See also:")
                       and not p.strip().startswith("## Key")
                       and not p.strip().startswith("-")]
        desc = ""
        if paragraphs:
            # First sentence of first paragraph
            first = paragraphs[0].replace("\n", " ")
            # Truncate at first period that's followed by a space
            for i, ch in enumerate(first):
                if ch == '.' and i < len(first) - 1 and first[i+1] == ' ':
                    desc = first[:i+1]
                    break
            if not desc:
                desc = first[:120] + "..."

        lines.append(f"- [{title}]({filename}) — {desc}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_wiki():
    """Generate all wiki pages and return list of (title, filename, content)."""
    catalog = load_catalog()
    indices = build_indices(catalog)

    WIKI_DIR.mkdir(exist_ok=True)

    pages = []
    for page_fn in WIKI_PAGES:
        title, filename, content = page_fn(catalog, indices)
        pages.append((title, filename, content))

    # Write pages
    for title, filename, content in pages:
        (WIKI_DIR / filename).write_text(content)

    # Write index
    index_content = generate_index(pages)
    (WIKI_DIR / "INDEX.md").write_text(index_content)

    return pages


if __name__ == "__main__":
    pages = generate_wiki()
    print(f"Generated {len(pages)} wiki pages + INDEX.md in wiki/\n")
    for title, filename, content in sorted(pages, key=lambda x: x[0]):
        size = len(content)
        lines = content.count('\n')
        print(f"  {filename:55s} {size:>6d} bytes  ({lines} lines)")

    index_size = (WIKI_DIR / "INDEX.md").stat().st_size
    print(f"\n  {'INDEX.md':55s} {index_size:>6d} bytes")
