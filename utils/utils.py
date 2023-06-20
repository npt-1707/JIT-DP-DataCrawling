import os
import math
from utils.line_parser import parse_lines
from utils.aggregator import aggregator
import subprocess
import re


def clone_repo(clone_path, name, url):
    """
    Clones a repository to the current directory
    """
    if name not in os.listdir(clone_path):
        command = "git clone {}"
        os.system(command.format(url))
    else:
        print(f"Existed '{name}' repository")
        command = "git pull"
        os.system(command)


def exec_cmd(command):
    """
    Get ouput of executing a command
    """
    # pip = os.popen(command)
    # output = pip.buffer.read().decode(encoding="utf8", errors="ignore")
    # output = output.strip("\n").split("\n") if output else []
    # return output
    result = subprocess.run(command, shell=True,
                            capture_output=True, text=False)
    output = result.stdout.strip(b"\n").split(b"\n") if result.stdout else []
    output = [line.decode(encoding="utf8", errors="replace")
              for line in output]
    return output


def get_commit_hashes(end):
    """
    Get commit hashes of a repository before `end`
    """
    command = 'git log --all --before={} --no-decorate --no-merges --pretty=format:"%H"'
    return exec_cmd(command.format(end))


def split_diff_log(file_diff_log):
    """
    Split the log of a commit into a list of diff
    """
    files_log, file_log = [], []
    for line in file_diff_log:
        if line[:10] == "diff --git":
            if file_log:
                files_log.append(file_log)
                file_log = []

        file_log.append(line)

    if file_log:
        files_log.append(file_log)

    return files_log


def is_numeric_string(string):
    # Regular expression pattern to match decimal numbers
    pattern = r"^[+-]?\d*\.?\d+$"

    # Check if the string matches the pattern
    return re.match(pattern, string) is not None


def process_one_line_blame(log):
    log = log.split()
    blame_id = log[0]
    while not is_numeric_string(log[1]):
        log.remove(log[1])
    blame_line_a = int(log[1])
    for idx, word in enumerate(log[2:]):
        if is_numeric_string(word):
            break
    idx = idx + 2
    blame_date = int(log[idx])
    blame_autor = " ".join(log[2:idx])[1:]
    blame_line_b = int(log[idx + 2][:-1])

    return {
        "blame_id": blame_id,
        "blame_line_a": blame_line_a,
        "blame_autor": blame_autor,
        "blame_date": blame_date,
        "blame_line_b": blame_line_b,
    }


def get_file_blame(file_blame_log):
    file_blame_log = [log.strip("\t").strip() for log in file_blame_log]
    id2line = {}
    for _, log in enumerate(file_blame_log):
        line_blame = process_one_line_blame(log)

        if not line_blame["blame_id"] in id2line:
            id2line[line_blame["blame_id"]] = {
                "id": line_blame["blame_id"],
                "author": line_blame["blame_autor"],
                "time": line_blame["blame_date"],
                "ranges": [],
            }

        idb = id2line[line_blame["blame_id"]]
        this_line = line_blame["blame_line_b"]
        ranges = idb["ranges"]
        if ranges:
            if this_line == ranges[-1]["end"] + 1:
                ranges[-1]["end"] += 1
            else:
                ranges.append({"start": this_line, "end": this_line})
        else:
            ranges.append({"start": this_line, "end": this_line})
    return id2line


def get_commit_info(commit_id, languages=[]):
    command = "git show {} --name-only --pretty=format:'%H%n%P%n%an%n%ct%n%s%n%B%n[ALL CHANGE FILES]'"
    show_msg = exec_cmd(command.format(commit_id))
    show_msg = [msg.strip() for msg in show_msg]
    file_index = show_msg.index("[ALL CHANGE FILES]")

    subject = show_msg[4]
    head = show_msg[:5]
    commit_msg = show_msg[5:file_index]
    # commit_files = show_msg[file_index + 1 :]

    parent_id = head[1]
    author = head[2]
    commit_date = head[3]
    commit_msg = " ".join(commit_msg)

    command = "git show {} --pretty=format: --unified=999999999"
    diff_log = split_diff_log(exec_cmd(command.format(commit_id)))
    commit_diff = {}
    commit_blame = {}
    files = []
    for log in diff_log:
        try:
            files_diff = aggregator(parse_lines(log))
        except:
            continue
        for file_diff in files_diff:
            file_name_a = (
                file_diff["from"]["file"]
                if file_diff["rename"] or file_diff["from"]["mode"] != "0000000"
                else file_diff["to"]["file"]
            )
            file_name_b = (
                file_diff["to"]["file"]
                if file_diff["rename"] or file_diff["to"]["mode"] != "0000000"
                else file_diff["from"]["file"]
            )
            if file_diff["is_binary"] or len(file_diff["content"]) == 0:
                continue

            if file_diff["from"]["mode"] == "000000000":
                continue

            if len(languages) > 0:
                file_language = get_programming_language(file_name_b)
                if file_language not in languages:
                    continue

            command = "git blame -t -n -l {} '{}'"
            file_blame_log = exec_cmd(command.format(parent_id, file_name_a))
            if not file_blame_log:
                continue
            file_blame = get_file_blame(file_blame_log)

            commit_blame[file_name_b] = file_blame
            commit_diff[file_name_b] = file_diff
            files.append(file_name_b)

    commit = {
        "commit_id": commit_id,
        "parent_id": parent_id,
        "subject": subject,
        "commit_msg": commit_msg,
        "author": author,
        "commit_date": int(commit_date),
        "files": files,
        "diff": commit_diff,
        "blame": commit_blame,
    }
    return commit


def find_file_author(blame, file_path):
    if not file_path in blame:
        return [], []
    author = set()
    commit = set()
    file_blame = blame[file_path]["id2line"]
    for elem in file_blame:
        name = file_blame[elem]["author"]
        commit.add(file_blame[elem]["id"])
        author.add(name)
    return list(commit), list(author)


# def calc_commit_ndev(commit_id, is_first=False):
#     '''
#     Count the number of developers in a commit
#     '''
#     if is_first:
#         command = "git log --pretty=format:%an {}"
#     else:
#         command = "git log --pretty=format:%an {}^.."
#     authors = set(exec_cmd(command.format(commit_id)))
#     return len(authors)


# def get_file_ndev(commit_id, file_path):
#     """
#     Count the number of developers in a file given a commit
#     """
#     # command = "git blame --show-email {} -- {} | sed 's/[(]//' | cut -d' ' -f2 | sort -u "
#     # authors = set(exec_cmd(command.format(commit_id, file_path)))
#     # return len(authors)
#     command = "git log --format=%an --follow {} -- {} | sort -u"
#     authors = set(exec_cmd(command.format(commit_id, file_path)))
#     return authors


# def calc_lt(commit_id, file_path):
#     return int(exec_cmd("git blame {} -- {} | wc -l".format(commit_id, file_path))[0])


def get_subs_dire_name(fileDirs):
    """
    Get the subsystem, directory, and file from a file path
    """
    fileDirs = fileDirs.split("/")
    if len(fileDirs) == 1:
        subsystem = "root"
        directory = "root"
    else:
        subsystem = fileDirs[0]
        directory = "/".join(fileDirs[0:-1])
    file_name = fileDirs[-1]

    return subsystem, directory, file_name


def calc_entrophy(totalLOCModified, locModifiedPerFile):
    """
    Calculate the entrophy
    """
    entrophy = 0
    for fileLocMod in locModifiedPerFile:
        if fileLocMod != 0:
            avg = fileLocMod / totalLOCModified
            entrophy -= avg * math.log(avg, 2)

    return entrophy


# def get_file_age(commit_id, file_path):
#     """
#     Calculate the age of file in a commit
#     """
#     command = "git blame --date=format-local:%s {} -- {} | cut -d' ' -f3 | sort -u"
#     date = exec_cmd(command)
#     if not date:
#         return 0
#     return max(map(int, date))


def check_fix(msg):
    # List of keywords indicating bug fixes
    bug_keywords = ["fix", "bug", "issue"]
    wrong_keywords = ["fix typo", "fix build", "non-fix"]
    if any(keyword in msg for keyword in bug_keywords):
        if not any(keyword in msg for keyword in wrong_keywords):
            return 1
    return 0


def get_prev_time(blame, file):
    if not file in blame:
        return 0

    max_time = 0
    for elem in blame[file].items():
        elem = elem[1]
        max_time = max(elem["time"], max_time)
    return max_time


def get_author_exp(author_exp):
    exp = 0
    for file in list(author_exp.items())[1:]:
        exp += len(file[1])
    return exp


def get_author_rexp(author_exp, now):
    rexp = 0
    for file in list(author_exp.items())[1:]:
        for t in file[1]:
            age = (now - t) / 86400
            age = max(age, 0)
            rexp += 1 / (age + 1)
    return rexp


def get_author_sexp(author_exp, subsystems):
    sexp = 0
    for file in author_exp.items():
        file_path = file[0]
        sub, _, _ = get_subs_dire_name(file_path)
        if sub in subsystems:
            sexp += 1
    return sexp


def calu_modified_lines(file):
    add_line, del_line = 0, 0
    t_line = file["meta_a"]["lines"] if "meta_a" in file else 0
    for ab in file["content"]:
        if "a" in ab:
            del_line += len(ab["a"])
        if "b" in ab:
            add_line += len(ab["b"])

    return add_line, del_line, t_line


def get_programming_language(file_path):
    extension = os.path.splitext(file_path)[1].lower()

    language_map = {
        ".py": "Python",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".js": "JavaScript",
        ".rb": "Ruby",
        ".swift": "Swift",
        ".go": "Go",
        ".rs": "Rust",
        ".ts": "TypeScript",
        ".php": "PHP",
        # ".html": "HTML",
        # ".css": "CSS",
        # ".pl": "Perl",
        # ".sh": "Bash",
        # ".lua": "Lua",
        # ".sql": "SQL",
        ".cc": "C++",
        # ".h": "C",
        # Add more extensions and programming languages as needed
    }

    return language_map.get(extension, None)
