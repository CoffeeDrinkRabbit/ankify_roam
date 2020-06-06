import os
import re
from itertools import zip_longest
import logging

# TODO: I think the extract_*  methods should be in the RoamObject class

RE_TAG = r"#[\w\-_@]+"
RE_PAGE_REF = "\[\[[^\[\]]*\]\]"

class RoamDb:
    def __init__(self):
        pass

    @classmethod
    def from_json(cls, page_jsons):
        roam_db = cls()
        pages = [Page.from_json(p, roam_db) for p in page_jsons]
        roam_db.add_pages(pages)
        return roam_db

    def add_pages(self, pages):
        self.pages = pages

    def get_tags(self, string):
        RE_PAGE_REF = "\[\[([^\[\]]+)\]\]"
        RE_TAG = "#([\w\d_\-@]+)"
        return list(set(re.findall(RE_PAGE_REF, string)+ re.findall(RE_TAG, string)))

    def get_block_by_uid(self, uid, blocks=None):
        if blocks is None: blocks = self.pages
        for block in blocks:
            if block.get("uid") == uid:
                return block
            block = self.get_block_by_uid(uid, block.get('children',[]))
            if block:
                return block

    def set_tags(self, objs=None, parent_tags=[]):
        if objs is None: objs=self.pages
        for obj in objs:
            if type(obj)==Block:
                obj.set_parent_tags(parent_tags)
            if obj.get("children"):
                self.set_tags(obj.get("children"), parent_tags=obj.get_tags())

    def get_blocks_by_tag(self, tag, objs=None):
        if objs is None: objs=self.pages
        blocks = []
        for obj in objs:
            if type(obj)==Block and tag in obj.get_tags():
                blocks.append(obj)
            blocks += self.get_blocks_by_tag(tag, obj.get("children",[]))
        return blocks

# Roam Interface
# --------------

class RoamInterface:
    def get_tags(self):
        raise NotImplementedError

    def to_string(self):
        raise NotImplementedError

    def to_html(self, *arg, **kwargs):
        raise NotImplementedError

# Roam Container
# ------------------------

class RoamObjectList(RoamInterface, list):
    def __init__(self, roam_objects):
        """
        Args:
            roam_objects (List of RoamObject)
        """
        for obj in roam_objects:
            self.append(obj)

    @classmethod
    def from_string(cls, string, *args, **kwargs):
        roam_objects = [String(string)]
        for rmobj_cls in [Cloze, Image, Alias, Checkbox, View, Button, PageRef, PageTag, BlockRef]:
            roam_objects = rmobj_cls.find_and_replace(roam_objects, *args, **kwargs)
        return cls(roam_objects)

    def get_tags(self):
        tags = []
        for obj in self:
            tags += obj.get_tags()
        return list(set(tags))

    def to_string(self):
        return "".join([o.to_string() for o in self])

    def to_html(self, *args, **kwargs):
        # TODO: implement filters
        html = "".join([o.to_html(*args, **kwargs) for o in self])
        html = self._markdown_to_html(html)
        return html 

    def is_single_pageref(self):
        return len(self)==1 and type(self[0])==PageRef

    def get_strings(self):
        return [o for o in self if type(o)==String]

    @staticmethod
    def _markdown_to_html(string):
        # TODO: haven't thought much about how this should work
        string = re.sub(r"`([^`]+)`", "<code>\g<1></code>", string)
        string = re.sub(r"\*\*([^\*]+)\*\*", "<b>\g<1></b>", string)
        string = re.sub(r"\_\_([^_]+)\_\_", "<em>\g<1></em>", string)
        string = re.sub(r"\^\^([^\^]+)\^\^", 
            '<span class="roam-highlight">\g<1></span>', string)

        return string

    def __repr__(self):
        return "<%s(%s)>" % (
            self.__class__.__name__, repr(list(self)))

class BlockList(list):
    def __init__(self, blocks=[]):
        for b in blocks:
            self.append(b)

    def _listify(self, blocks, *args, **kwargs):
        if blocks is None:
            return ""
        html = ""
        for block in blocks:
            content = block.to_html(*args, **kwargs) + \
                      self._listify(block.get("children"))
            html += "<li>" + content + "</li>"
        html = "<ul>" + html + "</ul>"
        return html

    def to_html(self, *args, **kwargs):
        if len(self)==0:
            return ""
        elif len(self)==1:
            return self[0].to_html(*args, **kwargs)
        else:
            html = self._listify(self, *args, **kwargs)
            #TODO: should this be a config?
            return '<div class="centered-block">' + html + '</div>'

class Block:
    def __init__(self, content, children=[], uid="", create_time="", 
                 create_email="",  edit_time="", edit_email="", roam_db=None):
        self.content = content # RoamObjectList
        self.children = children # BlockList
        self.uid = uid
        self.create_time = create_time
        self.create_email = create_email
        self.edit_time = edit_time
        self.edit_email = edit_email
        self.roam_db = roam_db
        self.parent_tags = []
        self.objects = []

    def set_parent_tags(self, parent_tags):
        self.parent_tags = parent_tags

    def get(self, key, default=BlockList()):
        return getattr(self, key) if hasattr(self, key) else default

    def get_tags(self):
        return list(set(self.parent_tags + self.content.get_tags()))

    def get_block_tags(self):
        return self.content.get_tags()

    def to_string(self):
        return self.content.to_string()

    def to_html(self, *args, **kwargs):
        return self.content.to_html(*args, **kwargs)

    @classmethod
    def from_json(cls, block, roam_db):
        # TODO: rename this
        content = RoamObjectList.from_string(block["string"], roam_db=roam_db)
        children = BlockList([Block.from_json(c, roam_db) for c in block.get("children",[])])
        return cls(content, children, block['uid'], block.get('create-time'),
                   block.get('create-email'), block.get('edit-time'), block.get('edit-email'), roam_db)

    @classmethod
    def from_string(cls, string, *args, **kwargs):
        content = RoamObjectList.from_string(string)
        return cls(content, *args, **kwargs)

    def __repr__(self):
        return "<%s(%s)>" % (
            self.__class__.__name__, list(self.content))

class Page:
    def __init__(self, title, children, edit_time, edit_email):
        self.title = title
        self.children = children
        self.edit_time = edit_time
        self.edit_email = edit_email

    def get_tags(self):
        return [self.title]

    def get(self, key, default=None):
        return getattr(self, key) if hasattr(self, key) else default

    @classmethod
    def from_json(cls, page, roam_db):
        children = [Block.from_json(c, roam_db) for c in page.get("children",[])]
        return cls(page['title'], children, page['edit-time'], page['edit-email'])


# Roam Objects
# -------------


class RoamObject(RoamInterface):
    @classmethod
    def from_string(cls, string, validate=True):
        if validate and not cls.validate_string(string):
            raise ValueError(f"Invalid string '{string}' for {cls.__name__}")

    @classmethod
    def validate_string(cls, string):
        roam_objects = RoamObjectList([String(string)])
        for pat in cls._create_patterns(roam_objects):
            if re.search("^"+pat+"$", string):
                return True
        return False

    @classmethod
    def _create_patterns(cls, roam_objects):
        "Return list of regex patterns for this type"
        raise NotImplementedError

    def to_string(self):
        raise NotImplementedError

    def to_html(self, *args, **kwargs):
        return self.string

    def get_tags(self):
        return []
    
    @classmethod
    def _find_and_replace(cls, string, pat, *args, **kwargs):
        "See the find_and_replace method"
        roam_objects = [cls.from_string(s, *args, **kwargs) for s in re.findall(pat, string)]
        string_split = [String(s) for s in re.split(pat, string)]
        # Weave strings and roam objects together 
        roam_objects = [a for b in zip_longest(string_split, roam_objects) for a in b if a]
        roam_objects = [o for o in roam_objects if o.to_string()]
        return roam_objects

    @classmethod
    def find_and_replace(cls, roam_objects, *args, **kwargs):
        """Replace all strings representing this object with this object

        Args:
            roam_objects: RoamObjectList or string
        """
        if type(roam_objects)==str: roam_objects = RoamObjectList([String(roam_objects)])
        pats = cls._create_patterns(roam_objects)
        for pat in pats:
            new_roam_objects = []
            for obj in roam_objects:
                if type(obj)==String:
                    new_roam_objects += cls._find_and_replace(obj.to_string(), pat, *args, **kwargs)
                else:
                    new_roam_objects += [obj]
            roam_objects = new_roam_objects

        return RoamObjectList(roam_objects)

    def __repr__(self):
        return "<%s(string='%s')>" % (
            self.__class__.__name__, self.to_string())

    def __eq__(self, b):
        return self.to_string()==b.to_string()


class Cloze(RoamObject):
    RE = r"(?<!}){c?\d*[:|]?[^{}]+}(?!})"
    ROAM_TEMPLATE = "{c%s:%s}"
    ANKI_TEMPLATE = "{{c%s::%s}}"

    def __init__(self, id, text):
        self.id = id
        self.text = text

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().from_string(string)
        id = cls._get_id(string)
        text = cls._get_text(string)
        return cls(id, text)

    @classmethod
    def find_and_replace(cls, roam_objects, *args, **kwargs):
        """
        Args:
            roam_objects (List[RoamObjects] or string)
        """
        roam_objects = super().find_and_replace(roam_objects)
        cls._assign_cloze_ids([o for o in roam_objects if type(o)==Cloze])
        return RoamObjectList(roam_objects)

    @classmethod
    def _create_patterns(cls, string):
        return [cls.RE] 

    def get_tags(self):
        return RoamObjectList.from_string(self.text).get_tags()

    def to_string(self, style="anki"):
        """
        Args:
            style (string): {'anki','roam'}
        """
        if style=="anki":
            return self.ANKI_TEMPLATE % (self.id, self.text)
        elif style=="roam":
            return self.ROAM_TEMPLATE % (self.id, self.text)
        else:
            raise ValueError(f"style='{style}' is an invalid. "\
                              "Must be 'anki' or 'roam'")

    def to_html(self, pageref_cloze="base_only"):
        """
        Args:
            pageref_cloze (str): {'outside', 'inside', 'base_only'}
        """
        roam_objects = RoamObjectList.from_string(self.text)
        if not roam_objects.is_single_pageref():
            return Cloze(self.id, roam_objects.to_html()).to_string()

        # Fancy options to move around the cloze when it's only around a PageRef
        pageref = roam_objects[0]

        if pageref_cloze=="outside":
            text = pageref.to_html()
            return Cloze(self.id, text).to_string()

        elif pageref_cloze=="inside":
            clozed_title = Cloze(self.id, pageref.title).to_string()
            return pageref.to_html(title=clozed_title)

        elif pageref_cloze=="base_only":
            clozed_base = Cloze(self.id, pageref.get_basename()).to_string()
            namespace = pageref.get_namespace()
            if namespace:
                clozed_base = namespace + "/" + clozed_base
            return pageref.to_html(title=clozed_base)

        else:
            raise ValueError(f"{pageref_cloze} is an invalid option for `pageref_cloze`")
        
    @staticmethod
    def _get_id(string):
        match = re.search("{c?(\d+)[:|]", string)
        if match: 
            return int(match.group(1))
        return None

    @staticmethod
    def _get_text(string):
        return re.sub("{c?\d+[:|]","{", string)[1:-1]

    @staticmethod
    def _assign_cloze_ids(clozes):
        assigned_ids = [c.id for c in clozes if c.id]
        next_id = 1
        for cloze in clozes:
            if cloze.id: continue
            while next_id in assigned_ids:
                next_id += 1
            assigned_ids += [next_id]
            cloze.id = next_id
    @staticmethod
    def _only_enclozes_pageref(roam_objects):
        return len(roam_objects)==1 and type(roam_objects[0])==PageRef

    def __repr__(self):
        return "<%s(id=%s, string='%s')>" % (
            self.__class__.__name__, self.id, self.string)


class Alias(RoamObject):
    RE_TEMPLATE = r"\[[^\[]+\]\(%s\)"
    def __init__(self, alias, destination):
        self.alias = alias
        self.destination = destination

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().from_string(string, validate)
        alias, destination = re.search(cls.RE, string).groups()
        if re.match("^\[\[.*\]\]$", destination):
            destination = PageRef(destination)
        elif re.match("^%s$" % BlockRef.RE, destination):
            destination = BlockRef(destination)
        else:
            destination = URL(destination)
        return cls(alias, destination)

    def to_string(self):
        return f"[{self.alias}]({self.destination.to_string()})"

    def to_html(self, *arg, **kwargs):
        if type(self.destination)==PageRef:
            return '<a title="page: %s" class="rm-alias rm-alias-page">%s</a>' % (
                self.destination.title, self.alias)
        elif type(self.destination)==BlockRef:
            return '<a title="block: %s" class="rm-alias rm-alias-block">%s</a>' % (
                self.destination.to_string(expand=True), self.alias)
        else:
            return '<a title="url: {0}" class="rm-alias rm-alias-external" href="{0}">{1}</a>'.format(
                self.destination.to_string(), self.alias)

    def get_tags(self):
        return self.destination.get_tags()
    
    @classmethod
    def _create_patterns(cls, roam_objects):
        pats = []
        page_refs = [p for o in roam_objects.get_strings() 
                       for p in PageRef.extract_page_ref_strings(o.to_string())]
        if page_refs:
            pats.append("|".join([cls.RE_TEMPLATE % re.escape(p) for p in page_refs]))
        pats.append(cls.RE_TEMPLATE % BlockRef.RE)
        pats.append(cls.RE_TEMPLATE % "[^\[\]\(\)]+")

        return pats


class String(RoamObject):
    def __init__(self, text):
        self.text = text

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().__init__(string, validate=True)
        return cls(string)

    @classmethod
    def validate_string(cls, string):
        return True

    def to_html(self, *arg, **kwargs):
        return self.text

    def get_tags(self):
        return []

    @classmethod
    def _create_patterns(cls, roam_objects):
        return [r".*","\n"]

    def to_string(self):
        return self.text


class View(RoamObject):
    RE_TEMPLATE = "{{%s:.*}}"
    def __init__(self, type, text, string=""):
        self.type = type
        self.text = text
        self.string = string

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().__init__(string, validate=True)
        type, text = re.search("{{([^:]*):(.*)}}", string).groups()
        type = re.sub("\[\[(.*)\]\]","\g<1>",type)
        return cls(type, text, string)

    @classmethod
    def validate_string(cls, string):
        return True

    def to_html(self, *arg, **kwargs):
        return self.text

    def get_tags(self):
        return []

    @classmethod
    def _create_patterns(cls, roam_objects):
        pats = []
        for view in ["youtube", "embed", "query", "mentions"]:
            pats.append(cls.RE_TEMPLATE % view)
            pats.append(cls.RE_TEMPLATE % re.escape(f"[[{view}]]"))
        return pats

    def to_string(self):
        return self.string


class Checkbox(RoamObject):
    def __init__(self, checked=False):
        self.checked = checked

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().from_string(string, validate)
        return cls(checked="DONE" in string)

    @classmethod
    def _create_patterns(cls, roam_objects=None):
        pats = [re.escape("{{[[%s]]}}" % s) for s in ['TODO','DONE']]
        return pats

    def get_tags(self):
        return ["DONE"] if self.checked else ["TODO"]

    def to_string(self):
        return "{{[[DONE]]}}" if self.checked else "{{[[TODO]]}}"

    def to_html(self, *arg, **kwargs):
        if self.checked:
            return '<span><label class="check-container"><input type="checkbox" checked=""><span class="checkmark"></span></label></span>'
        else:
            return '<span><label class="check-container"><input type="checkbox"><span class="checkmark"></span></label></span>'


class Button(RoamObject):
    RE = "{{.(?:(?<!{{).)*}}" 
    def __init__(self, name, text=""):
        self.name = name
        self.text = text

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().from_string(string, validate)
        contents = string[2:-2]
        if ":" in contents:
            m = re.search(r"(.*):(.*)", contents)
            name, text = m.groups()
        else:
            name, text = contents, ""
        return cls(name, text)

    def get_tags(self):
        return RoamObjectList(self.text).get_tags()

    def to_string(self):
        return "{{%s}}" % self.name

    def to_html(self, *arg, **kwargs):
        return '<button class="bp3-button bp3-small dont-focus-block">%s</button>' % self.text

    @classmethod
    def _create_patterns(cls, roam_objects=None):
        return [cls.RE]


def _get_page_ref_strings(string):
    # https://stackoverflow.com/questions/524548/regular-expression-to-detect-semi-colon-terminated-c-for-while-loops/524624#524624

    bracket_count = 0
    pages = []
    page = ""
    prev_char = ""
    for j,c in enumerate(string):
        # Track page opening and closing
        if prev_char+c == "[[":
            if not page:
                page = string[j-1]
            bracket_count += 1
            prev_char = ""
        elif prev_char+c == "]]":
            bracket_count -= 1
            prev_char = ""
        else:
            prev_char = c
        if page:
            page += c
        # End of page
        if bracket_count == 0 and page:
            pages.append(page)
            page = ""
            
    return pages


class PageRef(RoamObject):
    def __init__(self, title, uid=""):
        self.title = title
        self.uid = uid

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().__init__(string, validate)
        return cls(string[2:-2])

    @classmethod
    def _create_patterns(cls, roam_objects):
        page_refs = [p for o in roam_objects.get_strings() 
                       for p in PageRef.extract_page_ref_strings(o.to_string())]
        if page_refs:
            pat = "|".join([re.escape(p) for p in page_refs])
            return [pat]
        else:
            return []

    def get_tags(self):
        # TODO handle case of pages in pages
        return [self.title]

    def get_namespace(self):
        return os.path.split(self.title)[0]

    def get_basename(self):
        return os.path.split(self.title)[1]

    def to_string(self):
        return f"[[{self.title}]]"

    def to_html(self, title=None):
        if not title: title=self.title
        uid_attr = f' data-link-uid="{self.uid}"' if self.uid else ''
        return \
            f'<span data-link-title="{self.title}"{uid_attr}>'\
            f'<span class="rm-page-ref-brackets">[[</span>'\
            f'<span tabindex="-1" class="rm-page-ref rm-page-ref-link-color">{title}</span>'\
            f'<span class="rm-page-ref-brackets">]]</span>'\
            f'</span>'

    @staticmethod
    def extract_page_ref_strings(string):
        # https://stackoverflow.com/questions/524548/regular-expression-to-detect-semi-colon-terminated-c-for-while-loops/524624#524624
        bracket_count = 0
        pages = []
        page = ""
        prev_char = ""
        for j,c in enumerate(string):
            # Track page opening and closing
            if prev_char+c == "[[":
                if not page:
                    page = string[j-1]
                bracket_count += 1
                prev_char = ""
            elif prev_char+c == "]]":
                bracket_count -= 1
                prev_char = ""
            else:
                prev_char = c
            if page:
                page += c
            # End of page
            if bracket_count == 0 and page:
                pages.append(page)
                page = ""

        return pages


class PageTag(RoamObject):
    RE = r"#[\w\-_@]+"
    def __init__(self, text):
        self.text = text

    @classmethod
    def from_string(cls, string, validate=True, **kwargs):
        super().__init__(string, validate)
        return cls(string)

    @property
    def title(self):
        # Remove brackets, if any
        title = re.sub("#\[\[(.+)\]\]", '#\g<1>', self.text)
        return title[1:]

    def get_tags(self):
        return [self.title]

    def to_string(self):
        return self.text

    def to_html(self, *arg, **kwargs):
        return f'<span tabindex="-1" data-tag="{self.title}" '\
               f'class="rm-page-ref rm-page-ref-tag">#{self.title}</span>'

    @classmethod
    def _create_patterns(cls, roam_objects):
        pats = [cls.RE]
        # Create pattern for page refs which look like tags
        page_ref_pats = PageRef._create_patterns(roam_objects)
        if page_ref_pats:
            page_refs = page_ref_pats[0].split("|")
            pats.append("|".join(["#"+p for p in page_refs]))

        return pats


class BlockRef(RoamObject):
    RE = "\(\([\w\d\-_]{9}\)\)"
    def __init__(self, uid, roam_db=None):
        self.uid = uid
        self.roam_db = roam_db

    @classmethod
    def from_string(cls, string, **kwargs):
        super().from_string(string)
        roam_db = kwargs.get("roam_db", None)
        return cls(string[2:-2], roam_db)

    def to_string(self, expand=False):
        if expand:
            block = self.get_referenced_block()
            return block.to_string()
        else:
            return f"(({self.uid}))"

    def to_html(self, *arg, **kwargs):
        block = self.get_referenced_block()
        return '<div class="rm-block-ref"><span>%s</span></div>' % block.to_html()

    def get_tags(self):
        return []

    @classmethod
    def _create_patterns(cls, roam_objects=None):
        return [cls.RE]

    def get_referenced_block(self):
        return self.roam_db.get_block_by_uid(self.uid)

class URL(RoamObject):
    def __init__(self, text):
        self.text = text

    @classmethod
    def from_string(cls, string, **kwargs):
        super().__init__(string)
        return cls(string)

    def to_string(self):
        return self.text

    def to_html(self, *arg, **kwargs):
        return f'<span><a href="{self.text}">{self.text}</a></span>'


class Image(RoamObject):
    RE = r"!\[[^\[\]]*\]\([^()]*\)"
    def __init__(self, src, alt=""):
        self.src = src
        self.alt = alt

    @classmethod
    def from_string(cls, string, **kwargs):
        super().__init__(string)
        alt, src = re.search("!\[([^\[\]]*)\]\(([^()]*)\)", string).groups()
        return cls(src, alt)

    @classmethod
    def _create_patterns(cls, roam_objects):
        return [cls.RE]

    def to_html(self, *arg, **kwargs):
        return f'<img src="{self.src}" alt="{self.alt}" draggable="false" class="rm-inline-img">'


class CodeBlock(RoamObject):
    def __init__(self, string, **kwargs):
        super().__init__(string)




#    @staticmethod
#    def page_title_to_html(title):
#        return \
#            f'<span class="rm-page-ref-brackets">[[</span>'\
#            f'<span class="rm-page-ref-link-color">{title}</span>'\
#            f'<span class="rm-page-ref-brackets">]]</span>'
#
#    def to_html(self, **kwargs):
#        """
#        Args:
#            pageref_cloze (str): {'outside', 'inside', 'base_only'}
#        """
#        pageref_cloze = kwargs.get("pageref_cloze")
#        if not self.clozed:
#            return self.page_title_to_html(self.get_name())
#        if pageref_cloze=="outside":
#            page_html = self.page_title_to_html(self.get_name())
#            return Cloze.roam_encloze(self.cloze_id, page_html)
#        elif pageref_cloze=="inside":
#            page_cloze = Cloze.roam_encloze(self.cloze_id, self.get_name())
#            return self.page_title_to_html(page_cloze)
#        elif pageref_cloze=="base_only":
#            clozed_basename = Cloze.roam_encloze(self.cloze_id, self.get_basenamename())
#            namespace = self.get_namespace()
#            if namespace:
#                page_clozed_based = namespace + "/" + clozed_basename
#            else:
#                page_clozed_based = clozed_basename
#            return self.page_title_to_html(page_clozed_based)

    
