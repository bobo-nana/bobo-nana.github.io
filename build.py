import copy
import itertools
import pathlib
import re

import bs4
import yaml


class Site:

    def __init__(self, root_path: pathlib.Path) -> None:

        if not root_path.is_dir():
            raise ValueError(f"Invalid path. root_path: {root_path}")

        self._root_path = root_path
        self._nodes = {}

        self.create_base_nodes()
        self.create_index_nodes()

    def get_attr(self, path: str) -> dict:
        if path not in self._nodes:
            raise ValueError(f"Invalid path. path: {path}")

        return self._nodes[path].attr

    def create_base_nodes(self) -> None:
        for yaml_path in self._root_path.glob("**/_*.yaml"):
            html_name = yaml_path.name[1:-4] + "html"
            html_path = yaml_path.with_name(html_name)

            with (self._root_path / yaml_path).open("r") as yaml_file:
                content = yaml.safe_load(yaml_file)

            if content.get("type") != "data":
                content = {
                    **copy.deepcopy(content),
                    "type": "base",
                    "root_path": self._root_path,
                    "children": [content],
                }

            node = Node.create(html_path, content)

            self._nodes[node.path] = node

    def create_index_nodes(self) -> None:
        indexes = self.get_attr("/site.html").get("indexes", [])

        for index in indexes:
            page_root = index.get("path")
            page_size = index.get("page_size", 20)

            post_nodes = [
                self._nodes[path]
                for path in filter(lambda path: path.startswith(page_root), self._nodes)
            ]

            post_nodes.sort(key=lambda node: node.attr.get("date"), reverse=True)

            if post_nodes:
                (pathlib.Path("." + page_root) / "indexes").mkdir(parents=True, exist_ok=True)

            page_links = [
                f"{page_root}indexes/index_{i}.html"
                for i, _ in enumerate(range(0, len(post_nodes), page_size))]

            for i, chunked_post_nodes in enumerate(itertools.batched(post_nodes, page_size)):
                data = {
                    "type": "base",
                    "root_path": self._root_path,
                    "children": [
                        {
                            "type": "post_list",
                            "post_nodes": chunked_post_nodes,
                            "page_index": i,
                            "page_links": page_links,
                        }
                    ],
                }

                if index.get("home", False) and i == 0:
                    node = Node.create(pathlib.Path("./index.html"), copy.deepcopy(data))

                    self._nodes[node.path] = node

                index_path = pathlib.Path("." + page_root) / "indexes" / f"index_{i}.html"

                node = Node.create(index_path, data)

                self._nodes[node.path] = node


class Node:

    """
    - Every file with name starting with underscore is a node.
    - A node contains data and children.
        - data: The dictionary without the "children" key.
        - children: The values of the "children" key. Representing the child nodes of the node.
    """

    REGISTERED_NODE_TYPES = {}

    @staticmethod
    def register(node_class: type) -> type:
        node_class_name = "".join([
            ("_" if i > 0 and c.isupper() else "") + c.lower()
            for i, c in enumerate(node_class.__name__)
        ])

        if node_class_name.startswith("_"):
            node_class_name = node_class_name[1:]
        if node_class_name.endswith("_node"):
            node_class_name = node_class_name[:-5]

        Node.REGISTERED_NODE_TYPES[node_class_name] = node_class

        return node_class

    @staticmethod
    def create(path: pathlib.Path, data: dict) -> "Node":
        if "type" not in data:
            raise ValueError(f"Invalid data. data: {data}")

        node_class = Node.REGISTERED_NODE_TYPES[data["type"]]

        return node_class(path, data)

    @staticmethod
    def process_text(text: str) -> str:
        text = re.sub(r"__(.*?)__", r"<i>\1</i>", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', text)

        return text

    @staticmethod
    def process_url(html_path: pathlib.Path, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url

        if url.startswith("/"):
            return url

        return str(html_path.parent / url)

    def __init__(self, path: pathlib.Path, data: dict) -> None:
        children = data.pop("children", [])

        self._path = path
        self._attr = data
        self._children = [Node.create(path, child) for child in children]

    @property
    def attr(self) -> dict:
        return copy.deepcopy(self._attr)

    @property
    def path(self) -> str:
        return "/" + str(self._path)

    def render(self, site: Site) -> str:
        return "".join([child.render(site) for child in self._children])

    def render_children(self, site: Site) -> str:
        return "".join([child.render(site) for child in self._children])


@Node.register
class DataNode(Node):
    pass


@Node.register
class BaseNode(Node):

    def __init__(self, path: pathlib.Path, data: dict) -> None:
        super().__init__(path, data)

        self._html_path = data.get("root_path") / path

    def render(self, site: Site) -> str:
        if self._children and self._children[0].attr.get("title"):
            title = self._children[0].attr.get("title")
        else:
            title = site.get_attr("/site.html").get("name")

        head = HeadNode("/", {"title": title}).render(site)
        header = HeaderNode("/", {}).render(site)
        footer = FooterNode("/", {}).render(site)
        content = "".join([child.render(site) for child in self._children])

        html = f"""
            <!DOCTYPE html>
            <html lang="en" data-bs-theme="dark">
                {head}
                <body>
                { header }
                <main class="container w-75">
                    { content }
                </main>
                { footer }
                </body>
            </html>
            """
        
        html_formatter = bs4.formatter.HTMLFormatter(indent=4)

        html = bs4.BeautifulSoup(html, "html.parser").prettify(formatter=html_formatter)

        with (self._html_path).open("w") as html_file:
            html_file.write(html)

        return html


@Node.register
class HeadNode(Node):
    def render(self, site: Site) -> str:
        css_timeline = f"""
            .timeline {{
                border-left: 1px solid hsl(0, 0%, 80%);
                position: relative;
                list-style: none;
                margin-left: 25px;
                margin-right: 25px;
            }}

            .timeline .timeline-item {{
                position: relative;
            }}

            .timeline .timeline-item:after {{
                position: absolute;
                display: block;
                top: 0;
            }}

            .timeline .timeline-item:last-child:before {{
                content: '';
                position: absolute;
                left: -38px;
                bottom: 0;
                width: 11px;
                height: 11px;
                border-radius: 50%;
                background-color: hsl(217, 88.2%, 30%);
                border: 1px solid hsl(217, 88.2%, 60%);
            }}

            .timeline .timeline-icon {{
                position: absolute;
                left: -48px;
                background-color: hsl(217, 88.2%, 10%);
                color: hsl(217, 88.8%, 35.1%);
                border-radius: 50%;
                border: 1px solid hsl(217, 88.2%, 80%);
                height: 31px;
                width: 31px;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
        """

        title = self.attr.get(
            "title",
            site.get_attr("/site.html").get("name"),
        )

        return f"""
            <head>
                <meta charset="utf-8">
                <meta http-equiv="X-UA-Compatible" content="IE=edge">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta name="description" content="description">

                <title>{title}</title>

                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" crossorigin="anonymous"></script>
                <style>
                    body {{
                        min-height: 75rem;
                        padding-top: 4.5rem;
                    }}

                    {css_timeline}
                </style>
            </head>
        """


@Node.register
class HeaderNode(Node):

    def render(self, site: Site) -> str:
        attr = site.get_attr("/site.html")

        site_name = attr.get("name")

        page_list = []

        for page in attr.get("pages", []):
            if "link" in page:
                page_list.append(f"""
                    <li class="nav-item">
                        <a class="nav-link" href="{page.get("link")}">{page.get("name")}</a>
                    </li>
                    """)
            else:
                sub_page_list = "".join([
                    f"""
                    <li><a class="dropdown-item" href="{sub_page.get("link")}">{sub_page.get("name")}</a></li>
                    """
                    for sub_page in page.get("list", [])
                ])

                head = f"""
                    <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                        {page.get("name")}
                    </a>
                """

                page_list.append(f"""
                    <li class="nav-item dropdown">
                        {head}
                        <ul class="dropdown-menu">
                            {sub_page_list}
                        </ul>
                    </li>
                """)

        return f"""
            <nav class="navbar fixed-top navbar-expand-md bg-body-tertiary">
                <div class="container w-75">

                    <a class="navbar-brand" href="/">
                        {site_name}
                    </a>

                    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNavDropdown" aria-controls="navbarNavDropdown" aria-expanded="false" aria-label="Toggle navigation">
                        <span class="navbar-toggler-icon"></span>
                    </button>

                    <div class="collapse navbar-collapse justify-content-end" id="navbarNavDropdown">
                        <ul class="navbar-nav">
                            {''.join(page_list)}
                        </ul>
                    </div>

                </div>
            </nav>
        """


@Node.register
class FooterNode(Node):

    def render(self, site: Site) -> str:
        return ""


@Node.register
class PageNode(Node):
    def render(self, site: Site) -> str:
        title = self.attr.get("title")

        if authors := self.attr.get("authors", []):
            authors = ", ".join(authors)

            html_authors = f"""
                <span>
                    <i class="bi bi-person" style="font-size: 1rem; color: cornflowerblue;"></i>
                    {authors}
                </span>
            """
        else:
            html_authors = ""

        if tags := self.attr.get("tags"):
            tags = " ".join(
                f"<span class=\"badge rounded-pill text-bg-info\">{tag}</span>"
                for tag in tags)

            html_tags = f"""
                <span class="ms-3">
                    <i class="bi bi-tags" style="font-size: 1rem; color: cornflowerblue;"></i>
                    {tags}
                </span>
            """
        else:
            html_tags = ""

        content = super().render(site)

        return f"""
            <h1>{title}</h1>

            <div class="mb-4">
                {html_authors}
                {html_tags}
            </div>

            {content}
        """


@Node.register
class PostNode(Node):
    def render(self, site: Site) -> str:
        title = self.attr.get("title")
        authors = self.attr.get("authors", [])
        tags = self.attr.get("tags", [])

        authors = (", " if authors else "").join(authors)
        tags = map(lambda tag: f"""<span class="badge rounded-pill text-bg-info">{tag}</span>""", tags)
        tags = (" " if tags else "").join(tags)

        stamp = TimestampNode(self._path, {
            "date": self.attr.get("date", "????-??"),
        }).render(site)

        content = super().render(site)

        return f"""
            <h1>{title}</h1>

            <div class="mb-4">
                {stamp}

                <span class="ms-3">
                    <i class="bi bi-person" style="font-size: 1rem; color: cornflowerblue;"></i>
                    {authors}
                </span>

                <span class="ms-3">
                    <i class="bi bi-tags" style="font-size: 1rem; color: cornflowerblue;"></i>
                    {tags}
                </span>
            </div>

            {content}
        """


@Node.register
class H1Node(Node):
    def render(self, site: Site) -> str:
        return f"<h1 class=\"mb-2\">{self.attr.get('text')}</h1>"


@Node.register
class H2Node(Node):
    def render(self, site: Site) -> str:
        return f"<h2 class=\"mb-2\">{self.attr.get('text')}</h2>"


@Node.register
class H3Node(Node):
    def render(self, site: Site) -> str:
        return f"<h3 class=\"mb-2\">{self.attr.get('text')}</h3>"


@Node.register
class H4Node(Node):
    def render(self, site: Site) -> str:
        return f"<h4 class=\"mb-2\">{self.attr.get('text')}</h4>"


@Node.register
class H5Node(Node):
    def render(self, site: Site) -> str:
        return f"<h5 class=\"mb-2\">{self.attr.get('text')}</h5>"


@Node.register
class H6Node(Node):
    def render(self, site: Site) -> str:
        return f"<h6 class=\"mb-2\">{self.attr.get('text')}</h6>"


@Node.register
class PNode(Node):
    def render(self, site: Site) -> str:
        text = self.attr.get('text')
        text = Node.process_text(text)
        return f"<p class=\"mb-3\">{text}</p>"


@Node.register
class DividerNode(Node):
    def render(self, site: Site) -> str:
        return f"<hr class=\"my-4\">"


@Node.register
class ImgNode(Node):
    def render(self, site: Site) -> str:
        attr = self.attr
        src = attr.get("src", "#")
        alt = attr.get("alt", "")
        return f"""<img src="{src}" class="img-fluid w-100 rounded pb-4" alt="{alt}">"""


@Node.register
class FigureNode(Node):
    def render(self, site: Site) -> str:
        attr = self.attr
        src = attr.get("src", "#")
        caption = attr.get("caption", "")

        return f"""
            <figure class="figure w-100 mb-3">
                <img src="{src}" class="figure-img img-fluid w-100 rounded" alt="{caption}" />
                <figcaption class="figure-caption">{caption}</figcaption>
            </figure>"""


@Node.register
class VideoNode(Node):
    def render(self, site: Site) -> str:
        attr = self.attr
        src = attr.get("src", "#")
        caption = attr.get("caption", "")

        # return f"""
        #     <div class="ratio ratio-16x9 mb-3">
        #         <iframe src="{src}" title="{caption}" frameborder="0" allowfullscreen></iframe>
        #     </div>"""

        return f"""
            <figure class="figure w-100 mb-3">
                <div class="ratio ratio-16x9">
                    <iframe src="{src}" title="{caption}" frameborder="0" allowfullscreen></iframe>
                </div>
                <figcaption class="figure-caption">{caption}</figcaption>
            </figure>"""


@Node.register
class TimestampNode(Node):
    def render(self, site: Site) -> str:
        attr = self.attr
        date = attr.get("date", "")
        time = attr.get("time", "")

        if date:
            html = f"""
                <span class="text-muted pb-2">
                    <i class="bi bi-calendar-event me-1" style="font-size: 1rem; color: cornflowerblue;"></i>
                    {date} {time}
                </span>
            """
        elif time:
            html = f"""
                <span class="text-muted pb-2">
                    <i class="bi bi-clock me-1" style="font-size: 1rem; color: cornflowerblue;"></i>
                    {time}
                </span>
            """
        else:
            html = ""

        return html


@Node.register
class PostListNode(Node):
    def render(self, site: Site) -> str:
        attr = self.attr

        post_nodes = attr.get("post_nodes", [])
        page_index = attr.get("page_index", 0)
        page_links = attr.get("page_links", [])

        post_list = "".join([
            f"""
            <div class="mb-4">
                <a class="text-decoration-none" href="{post_node.path}">
                    <h2 class="card-title mb-1">{post_node.attr.get("title")}</h2>

                    <span>
                        <i class="bi bi-calendar-event me-1" style="font-size: 1rem; color: cornflowerblue;"></i>
                        {post_node.attr.get("date")}
                    </span>
                    <span class="mx-1">By</span>
                    <span>
                        <i class="bi bi-person mx-1" style="font-size: 1rem; color: cornflowerblue;"></i>
                        {", ".join(post_node.attr.get("authors", []))}
                    </span>
                </a>
            </div>
            """
            for post_node in post_nodes
        ])

        if len(page_links) > 1:
            pagination_list = "".join([
                f"""
                <li class="page-item {'active' if index == page_index else ''}">
                    <a class="page-link" href="{link}">{index}</a>
                </li>
                """
                for index, link in enumerate(page_links)
            ])

            if page_index > 0:
                prev_link = page_links[page_index - 1]
                prev_enabled = ""
            else:
                prev_link = "#"
                prev_enabled = "disabled"

            if page_index < len(page_links) - 1:
                next_link = page_links[page_index + 1]
                next_enabled = ""
            else:
                next_link = "#"
                next_enabled = "disabled"

            pagination = f"""
                <hr class="my-4">
                <nav>
                    <ul class="pagination">
                        <li class="page-item">
                            <a class="page-link {prev_enabled}" href="{prev_link}">&laquo;</a>
                        </li>
                        {pagination_list}
                        <li class="page-item">
                            <a class="page-link {next_enabled}" href="{next_link}">&raquo;</a>
                        </li>
                    </ul>
                </nav>
            """
        else:
            pagination = ""

        return f"""
            <h3 class="mb-4">Posts</h3>
            {post_list}
            {pagination}
        """


@Node.register
class TimelineNode(Node):
    def render(self, site: Site) -> str:
        return f"""
        <div class="py-5">
            <ul class="timeline">
                {''.join([child.render(site) for child in self._children])}
            </ul>
        </div>
        """

@Node.register
class TimelineItemNode(Node):
    def render(self, site: Site) -> str:
        attr = self.attr

        icon = f"""<span class="timeline-icon">{attr.get("icon", "✅")}</span>"""

        name = attr.get("name", "")
        children = self.render_children(site)

        name = f"""<h5 class="fw-bold">{name}</h5>"""

        stamp = TimestampNode(self._path, {
            "date": attr.get("date", ""),
            "time": attr.get("time", ""),
        }).render(site)

        return f"""
            <li class="timeline-item mb-4">
                {icon}
                {name}
                {stamp}
                {"<div class=\"mb-3\"></div>" if children else ""}
                {children}
            </li>
        """


@Node.register
class TableNode(Node):
    def render(self, site: Site) -> str:
        attr = self.attr

        mods = attr.get("mods", [])
        head = attr.get("data", {}).get("head", [])
        body = attr.get("data", {}).get("body", [])

        table_class = "table"

        if "bordered" in mods:
            table_class += " table-bordered"

        if "hover" in mods:
            table_class += " table-hover"

        if "striped" in mods:
            table_class += " table-striped"

        html = f"<table class=\"{table_class} pb-2\">"

        if head:
            thead = "".join("<th scope=\"col\">" + str(col) + "</th>" for col in head)

            html += f"<thead><tr>{thead}</tr></thead>"

        if body:
            html += "<tbody>"

            for row in body:
                tr = "".join("<td>" + str(col) + "</td>" for col in row)

                html += f"<tr>{tr}</tr>"

            html += "</tbody>"

        html += "</table>"

        return html


if __name__ == "__main__":
    site = Site(pathlib.Path("."))

    for key, node in site._nodes.items():
        print(key, node.path)

    for node in site._nodes.values():
        node.render(site)
