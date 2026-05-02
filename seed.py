from app import app, db, User, Group, GroupMembership, GroupInvite
import secrets
import sys

print(f"Database path: {app.config['SQLALCHEMY_DATABASE_URI']}")

with app.app_context():
    try:
        db.drop_all()
        db.create_all()
    except Exception as e:
        print(f"ERROR dropping/creating tables: {e}")
        sys.exit(1)

    # --- Users ---
    # All passwords are: password123
    users_data = [
        ("Alice Chen",     "alice@bookclub.test",    "mystery, thriller"),
        ("Bob Ramirez",    "bob@bookclub.test",      "science fiction, fantasy"),
        ("Carol Kim",      "carol@bookclub.test",    "romance, fiction"),
        ("Dave Patel",     "dave@bookclub.test",     "non-fiction, history"),
        ("Emma Torres",    "emma@bookclub.test",     "classic literature, poetry"),
        ("Frank Nguyen",   "frank@bookclub.test",    "science fiction, horror"),
        ("Grace Liu",      "grace@bookclub.test",    "biography, self-help"),
        ("Henry Okafor",   "henry@bookclub.test",    "mystery, classic literature"),
        ("Isabel Marte",   "isabel@bookclub.test",   "romance, young adult"),
        ("James Park",     "james@bookclub.test",    "science fiction, non-fiction"),
        ("Kira Andersen",  "kira@bookclub.test",     "mystery, horror"),
        ("Leo Vasquez",    "leo@bookclub.test",      "fantasy, science fiction"),
        ("Mia Johansson",  "mia@bookclub.test",      "classic literature, biography"),
        ("Noah Osei",      "noah@bookclub.test",     "non-fiction, history"),
    ]

    users = []
    for name, email, prefs in users_data:
        u = User(name=name, email=email, preferences=prefs)
        u.set_password("password123")
        db.session.add(u)
        users.append(u)

    db.session.flush()

    alice, bob, carol, dave, emma, frank, grace, henry, isabel, james, kira, leo, mia, noah = users

    # --- Groups ---
    groups_data = [
        {
            "name": "Mystery Lovers Club",
            "description": "We devour whodunits, thrillers, and all things suspenseful.",
            "genre": "Mystery & Thriller",
            "reading_pace": "Casual (1 book/month)",
            "current_book": "The Thursday Murder Club",
            "up_next": "In the Woods",
            "completed_books": "Gone Girl\nThe Girl with the Dragon Tattoo\nBig Little Lies",
            "creator": alice,
        },
        {
            "name": "Sci-Fi Explorers",
            "description": "From hard sci-fi to space opera — we read it all.",
            "genre": "Science Fiction",
            "reading_pace": "Moderate (2 books/month)",
            "current_book": "Project Hail Mary",
            "up_next": "Dune Messiah",
            "completed_books": "Dune\nThe Martian\nAnnihilation\nNeuromancer",
            "creator": bob,
        },
        {
            "name": "Classic Lit Society",
            "description": "Tackling the great works, one century at a time.",
            "genre": "Classic Literature",
            "reading_pace": "Casual (1 book/month)",
            "current_book": "Middlemarch",
            "up_next": "Anna Karenina",
            "completed_books": "Pride and Prejudice\nJane Eyre\nGreat Expectations",
            "creator": emma,
        },
        {
            "name": "Non-Fiction Nerds",
            "description": "Real stories, real ideas, real impact.",
            "genre": "Non-Fiction",
            "reading_pace": "Casual (1 book/month)",
            "current_book": "Educated",
            "up_next": "The Body: A Guide for Occupants",
            "completed_books": "Sapiens\nBecoming\nThink Again",
            "creator": dave,
        },
        {
            "name": "Romance Readers",
            "description": "HEAs only. We stan a slow burn.",
            "genre": "Romance",
            "reading_pace": "Fast (1 book/week)",
            "current_book": "Beach Read",
            "up_next": "The Hating Game",
            "completed_books": "The Kiss Quotient\nIt Ends with Us",
            "creator": carol,
        },
    ]

    groups = []
    for g in groups_data:
        group = Group(
            name=g["name"],
            description=g["description"],
            genre=g["genre"],
            reading_pace=g["reading_pace"],
            current_book=g["current_book"],
            up_next=g["up_next"],
            completed_books=g["completed_books"],
            creator_id=g["creator"].id,
        )
        db.session.add(group)
        groups.append(group)

    db.session.flush()

    mystery, scifi, classics, nonfiction, romance = groups

    # --- Memberships ---
    # Format: (user, group, status)
    memberships = [
        # Mystery: Alice creator; Henry, Grace, Kira, Noah joined; Bob and Frank pending
        (alice,  mystery,    "approved"),
        (henry,  mystery,    "approved"),
        (grace,  mystery,    "approved"),
        (kira,   mystery,    "approved"),
        (noah,   mystery,    "approved"),
        (bob,    mystery,    "pending"),
        (frank,  mystery,    "pending"),

        # Sci-Fi: Bob creator; Frank, Alice, James, Leo, Kira, Noah all joined (7 total)
        (bob,    scifi,      "approved"),
        (frank,  scifi,      "approved"),
        (alice,  scifi,      "approved"),
        (james,  scifi,      "approved"),
        (leo,    scifi,      "approved"),
        (kira,   scifi,      "approved"),
        (noah,   scifi,      "approved"),
        (dave,   scifi,      "pending"),
        (mia,    scifi,      "pending"),

        # Classics: Emma creator; Henry, Carol, Mia, Grace joined; Isabel pending
        (emma,   classics,   "approved"),
        (henry,  classics,   "approved"),
        (carol,  classics,   "approved"),
        (mia,    classics,   "approved"),
        (grace,  classics,   "approved"),
        (isabel, classics,   "pending"),

        # Non-Fiction: Dave creator; Grace, Noah, James, Mia joined; Emma and Carol pending
        (dave,   nonfiction, "approved"),
        (grace,  nonfiction, "approved"),
        (noah,   nonfiction, "approved"),
        (james,  nonfiction, "approved"),
        (mia,    nonfiction, "approved"),
        (emma,   nonfiction, "pending"),
        (carol,  nonfiction, "pending"),

        # Romance: Carol creator; Emma, Alice, Isabel, Grace joined; Henry pending
        (carol,  romance,    "approved"),
        (emma,   romance,    "approved"),
        (alice,  romance,    "approved"),
        (isabel, romance,    "approved"),
        (grace,  romance,    "approved"),
        (henry,  romance,    "pending"),
        (mia,    romance,    "pending"),
    ]

    for user, group, status in memberships:
        db.session.add(GroupMembership(user_id=user.id, group_id=group.id, status=status))

    # --- Pending email invites (unused, so they can be accepted) ---
    invites = [
        (mystery,   "newmember1@bookclub.test"),
        (scifi,     "newmember2@bookclub.test"),
        (classics,  "leo@bookclub.test"),
        (romance,   "newmember3@bookclub.test"),
    ]

    for group, email in invites:
        db.session.add(GroupInvite(group_id=group.id, email=email, token=secrets.token_urlsafe(32), used=False))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"ERROR committing data: {e}")
        sys.exit(1)

    print("Database seeded!")
    print()
    print("Accounts (all passwords: password123)")
    print("--------------------------------------")
    for name, email, _ in users_data:
        print(f"  {email:<30} {name}")
