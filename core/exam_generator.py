"""
ResumeXpert – Exam Generator
Generates a skill-based multiple-choice quiz from the matched/resume skills.
"""

import random


# ---------------------------------------------------------------------------
# Question bank  (skill → list of question dicts)
# Each question: {q, a, b, c, d, correct}   correct ∈ {'a','b','c','d'}
# ---------------------------------------------------------------------------
QUESTION_BANK = {

    # ------------------------------------------------------------------ Python
    "python": [
        {
            "q": "Which data structure in Python is ordered and mutable?",
            "a": "Tuple", "b": "List", "c": "Set", "d": "Dictionary",
            "correct": "b",
            "explanation": "Lists are ordered and mutable. Tuples are ordered but immutable."
        },
        {
            "q": "What is the output of `print(type([]))`?",
            "a": "<class 'tuple'>", "b": "<class 'dict'>",
            "c": "<class 'list'>", "d": "<class 'set'>",
            "correct": "c",
            "explanation": "`[]` creates an empty list, so `type([])` returns `<class 'list'>`."
        },
        {
            "q": "Which keyword is used to define a function in Python?",
            "a": "func", "b": "function", "c": "define", "d": "def",
            "correct": "d",
            "explanation": "The `def` keyword is used to define functions in Python."
        },
        {
            "q": "What does `len('hello')` return?",
            "a": "4", "b": "5", "c": "6", "d": "None",
            "correct": "b",
            "explanation": "'hello' has 5 characters, so `len('hello')` returns 5."
        },
        {
            "q": "Which of these is used for list comprehension?",
            "a": "()", "b": "{}", "c": "[]", "d": "<>",
            "correct": "c",
            "explanation": "List comprehensions use square brackets `[]`."
        },
        {
            "q": "What is a lambda function in Python?",
            "a": "A named multi-line function", "b": "A recursive function",
            "c": "An anonymous inline function", "d": "A class method",
            "correct": "c",
            "explanation": "Lambda creates small anonymous functions: `lambda x: x + 1`."
        },
        {
            "q": "Which module is used for regular expressions in Python?",
            "a": "regex", "b": "re", "c": "regexp", "d": "pattern",
            "correct": "b",
            "explanation": "The built-in `re` module handles regular expressions in Python."
        },
        {
            "q": "What does `range(1, 5)` produce?",
            "a": "[1, 2, 3, 4, 5]", "b": "[0, 1, 2, 3, 4]",
            "c": "[1, 2, 3, 4]", "d": "[1, 2, 3, 4, 5, 6]",
            "correct": "c",
            "explanation": "`range(1, 5)` generates numbers from 1 up to (not including) 5."
        },
    ],

    # ------------------------------------------------------------------ Java
    "java": [
        {
            "q": "Which concept allows a class to inherit from multiple interfaces in Java?",
            "a": "Multiple inheritance", "b": "Polymorphism",
            "c": "Interface implementation", "d": "Abstraction",
            "correct": "c",
            "explanation": "Java allows a class to implement multiple interfaces."
        },
        {
            "q": "What is the default value of an int variable in Java?",
            "a": "null", "b": "undefined", "c": "1", "d": "0",
            "correct": "d",
            "explanation": "In Java, instance int fields default to 0."
        },
        {
            "q": "Which of these is NOT a Java access modifier?",
            "a": "public", "b": "private", "c": "protected", "d": "friend",
            "correct": "d",
            "explanation": "`friend` is a C++ concept; Java uses public, private, and protected."
        },
        {
            "q": "What does JVM stand for?",
            "a": "Java Virtual Machine", "b": "Java Variable Method",
            "c": "Java Verified Module", "d": "Joint Virtual Manager",
            "correct": "a",
            "explanation": "JVM (Java Virtual Machine) executes Java bytecode."
        },
    ],

    # ------------------------------------------------------------------ SQL
    "sql": [
        {
            "q": "Which SQL clause filters rows AFTER aggregation?",
            "a": "WHERE", "b": "HAVING", "c": "GROUP BY", "d": "ORDER BY",
            "correct": "b",
            "explanation": "HAVING filters groups produced by GROUP BY; WHERE filters rows before grouping."
        },
        {
            "q": "Which JOIN returns all rows from both tables?",
            "a": "INNER JOIN", "b": "LEFT JOIN", "c": "RIGHT JOIN", "d": "FULL OUTER JOIN",
            "correct": "d",
            "explanation": "FULL OUTER JOIN returns all rows from both tables, with NULLs where there's no match."
        },
        {
            "q": "What does `SELECT DISTINCT` do?",
            "a": "Orders results", "b": "Removes duplicate rows",
            "c": "Filters NULL values", "d": "Groups rows",
            "correct": "b",
            "explanation": "DISTINCT eliminates duplicate rows from the result set."
        },
        {
            "q": "Which keyword is used to sort results in ascending order?",
            "a": "SORT BY", "b": "ORDER BY ASC", "c": "ARRANGE BY", "d": "GROUP ASC",
            "correct": "b",
            "explanation": "ORDER BY column ASC sorts results in ascending order (ASC is the default)."
        },
    ],

    # --------------------------------------------------------- Machine Learning
    "machine learning": [
        {
            "q": "What is overfitting in machine learning?",
            "a": "Model has high bias on training data",
            "b": "Model performs well on training data but poorly on new data",
            "c": "Model is too simple to capture patterns",
            "d": "Model trains too slowly",
            "correct": "b",
            "explanation": "Overfitting means the model memorised training data and cannot generalise."
        },
        {
            "q": "Which algorithm is best for predicting a continuous value?",
            "a": "Logistic Regression", "b": "K-Means",
            "c": "Linear Regression", "d": "Decision Tree Classifier",
            "correct": "c",
            "explanation": "Linear Regression is used for continuous (numeric) output prediction."
        },
        {
            "q": "What does the term 'epoch' mean in neural network training?",
            "a": "One forward pass through a batch",
            "b": "One complete pass through the entire training dataset",
            "c": "One layer of the neural network",
            "d": "One update of model weights",
            "correct": "b",
            "explanation": "An epoch = one full pass over all training samples."
        },
        {
            "q": "Which metric is most suitable for imbalanced classification?",
            "a": "Accuracy", "b": "F1-Score", "c": "Mean Squared Error", "d": "R-Squared",
            "correct": "b",
            "explanation": "F1-Score balances precision and recall, making it suitable for imbalanced datasets."
        },
        {
            "q": "What is the purpose of the train-test split?",
            "a": "To increase model accuracy",
            "b": "To evaluate model performance on unseen data",
            "c": "To speed up training",
            "d": "To reduce dataset size",
            "correct": "b",
            "explanation": "A test split ensures the model is evaluated on data it has never seen during training."
        },
    ],

    # --------------------------------------------------------------- Deep Learning
    "deep learning": [
        {
            "q": "What activation function outputs values between 0 and 1?",
            "a": "ReLU", "b": "Tanh", "c": "Sigmoid", "d": "Leaky ReLU",
            "correct": "c",
            "explanation": "Sigmoid maps any input to a value between 0 and 1."
        },
        {
            "q": "What is a Convolutional Neural Network (CNN) primarily used for?",
            "a": "Time-series prediction", "b": "Natural language processing",
            "c": "Image recognition", "d": "Reinforcement learning",
            "correct": "c",
            "explanation": "CNNs excel at processing grid-like data such as images."
        },
        {
            "q": "What does dropout do in a neural network?",
            "a": "Increases learning rate",
            "b": "Randomly disables neurons during training to prevent overfitting",
            "c": "Removes low-importance features",
            "d": "Applies L2 regularisation",
            "correct": "b",
            "explanation": "Dropout randomly zeroes neuron outputs during training, acting as regularisation."
        },
    ],

    # --------------------------------------------------------------- Django
    "django": [
        {
            "q": "Which file in a Django app defines the database models?",
            "a": "views.py", "b": "urls.py", "c": "models.py", "d": "forms.py",
            "correct": "c",
            "explanation": "models.py contains Django ORM model class definitions."
        },
        {
            "q": "Which command applies pending database migrations in Django?",
            "a": "python manage.py migrate", "b": "python manage.py syncdb",
            "c": "python manage.py update", "d": "python manage.py dbinit",
            "correct": "a",
            "explanation": "`manage.py migrate` applies all pending migrations to the database."
        },
        {
            "q": "What is the purpose of `urls.py` in a Django project?",
            "a": "Define database schema", "b": "Map URL patterns to view functions",
            "c": "Configure templates", "d": "Handle form validation",
            "correct": "b",
            "explanation": "urls.py routes incoming HTTP requests to the appropriate view."
        },
        {
            "q": "Which Django class-based view is used to display a list of objects?",
            "a": "DetailView", "b": "FormView", "c": "ListView", "d": "CreateView",
            "correct": "c",
            "explanation": "ListView automatically queries and renders a queryset of objects."
        },
    ],

    # --------------------------------------------------------------- React
    "react": [
        {
            "q": "What hook is used to manage state in a React functional component?",
            "a": "useEffect", "b": "useRef", "c": "useContext", "d": "useState",
            "correct": "d",
            "explanation": "`useState` declares a state variable and a function to update it."
        },
        {
            "q": "What is JSX?",
            "a": "A JavaScript testing framework",
            "b": "A syntax extension for writing HTML-like code inside JavaScript",
            "c": "A CSS preprocessor",
            "d": "A React state manager",
            "correct": "b",
            "explanation": "JSX lets you write HTML-like markup inside JavaScript files."
        },
        {
            "q": "Which lifecycle-equivalent hook runs after every render in React?",
            "a": "useState", "b": "useCallback", "c": "useEffect", "d": "useMemo",
            "correct": "c",
            "explanation": "`useEffect` runs after every render (or conditionally based on dependencies)."
        },
    ],

    # --------------------------------------------------------------- JavaScript
    "javascript": [
        {
            "q": "Which keyword declares a block-scoped variable in modern JavaScript?",
            "a": "var", "b": "let", "c": "def", "d": "dim",
            "correct": "b",
            "explanation": "`let` (and `const`) are block-scoped; `var` is function-scoped."
        },
        {
            "q": "What does `===` check in JavaScript?",
            "a": "Value only", "b": "Type only",
            "c": "Value and type (strict equality)", "d": "Reference equality",
            "correct": "c",
            "explanation": "`===` checks both value and type; `==` performs type coercion."
        },
        {
            "q": "What is a Promise in JavaScript?",
            "a": "A synchronous callback",
            "b": "An object representing the eventual result of an async operation",
            "c": "A CSS animation",
            "d": "A variable declaration",
            "correct": "b",
            "explanation": "Promises represent async operations and can be in pending, fulfilled, or rejected states."
        },
    ],

    # --------------------------------------------------------------- HTML / CSS
    "html": [
        {
            "q": "Which HTML tag is used to create a hyperlink?",
            "a": "<link>", "b": "<a>", "c": "<href>", "d": "<url>",
            "correct": "b",
            "explanation": "The `<a>` (anchor) tag creates hyperlinks in HTML."
        },
        {
            "q": "Which attribute specifies the URL in an anchor tag?",
            "a": "src", "b": "link", "c": "href", "d": "url",
            "correct": "c",
            "explanation": "The `href` attribute holds the URL destination of the link."
        },
    ],

    "css": [
        {
            "q": "Which CSS property controls the space between the element border and content?",
            "a": "margin", "b": "border-spacing", "c": "gap", "d": "padding",
            "correct": "d",
            "explanation": "`padding` is the space inside the border; `margin` is outside."
        },
        {
            "q": "How do you select an element with id 'header' in CSS?",
            "a": ".header", "b": "*header", "c": "#header", "d": "&header",
            "correct": "c",
            "explanation": "IDs are selected with `#` in CSS."
        },
    ],

    # --------------------------------------------------------------- Docker / Cloud
    "docker": [
        {
            "q": "What is a Docker image?",
            "a": "A running container instance",
            "b": "A snapshot/blueprint used to create containers",
            "c": "A virtual machine",
            "d": "A package manager",
            "correct": "b",
            "explanation": "Images are immutable templates; containers are running instances of images."
        },
        {
            "q": "Which command lists all running Docker containers?",
            "a": "docker images", "b": "docker ps", "c": "docker run", "d": "docker list",
            "correct": "b",
            "explanation": "`docker ps` lists running containers; `docker ps -a` lists all."
        },
    ],

    "git": [
        {
            "q": "Which command creates a new branch in Git?",
            "a": "git add branch", "b": "git clone", "c": "git branch <name>", "d": "git push",
            "correct": "c",
            "explanation": "`git branch <name>` creates a new branch. Use `-b` with `checkout` to also switch."
        },
        {
            "q": "What does `git stash` do?",
            "a": "Deletes uncommitted changes",
            "b": "Saves uncommitted changes temporarily",
            "c": "Merges two branches",
            "d": "Pushes code to remote",
            "correct": "b",
            "explanation": "`git stash` shelves changes so you can work on something else."
        },
    ],

    # --------------------------------------------------------------- Data Science
    "data analysis": [
        {
            "q": "Which pandas method shows basic statistics of a DataFrame?",
            "a": "df.info()", "b": "df.head()", "c": "df.describe()", "d": "df.shape",
            "correct": "c",
            "explanation": "`df.describe()` returns count, mean, std, min, max, and quartiles."
        },
        {
            "q": "How do you drop rows with missing values in pandas?",
            "a": "df.remove_na()", "b": "df.dropna()", "c": "df.fillna()", "d": "df.isnull()",
            "correct": "b",
            "explanation": "`df.dropna()` removes rows (or columns) that contain NaN values."
        },
    ],

    "numpy": [
        {
            "q": "Which NumPy function creates an array of zeros?",
            "a": "np.empty()", "b": "np.ones()", "c": "np.zeros()", "d": "np.full()",
            "correct": "c",
            "explanation": "`np.zeros(shape)` returns a new array filled with zeros."
        },
    ],

    "tensorflow": [
        {
            "q": "Which TensorFlow class is used to build a sequential neural network?",
            "a": "tf.Model", "b": "tf.Layer", "c": "tf.keras.Sequential", "d": "tf.NeuralNet",
            "correct": "c",
            "explanation": "`tf.keras.Sequential` stacks layers linearly to build a model."
        },
    ],

    "scikit-learn": [
        {
            "q": "Which sklearn function splits data into train and test sets?",
            "a": "train_test_divide", "b": "cross_val_score",
            "c": "train_test_split", "d": "split_data",
            "correct": "c",
            "explanation": "`train_test_split` from sklearn.model_selection splits data randomly."
        },
        {
            "q": "What does `model.fit(X_train, y_train)` do?",
            "a": "Makes predictions", "b": "Evaluates the model",
            "c": "Trains the model on training data", "d": "Imports the model",
            "correct": "c",
            "explanation": "`.fit()` trains the model by learning patterns from training data."
        },
    ],

    # --------------------------------------------------------------- AWS / Cloud
    "aws": [
        {
            "q": "What does S3 stand for in AWS?",
            "a": "Simple Storage Service", "b": "Scalable Server System",
            "c": "Secure Streaming Service", "d": "Standard Storage Solution",
            "correct": "a",
            "explanation": "Amazon S3 (Simple Storage Service) is an object storage service."
        },
        {
            "q": "Which AWS service is used to run serverless functions?",
            "a": "EC2", "b": "S3", "c": "Lambda", "d": "RDS",
            "correct": "c",
            "explanation": "AWS Lambda runs code without provisioning or managing servers."
        },
    ],

    # --------------------------------------------------------------- NLP
    "natural language processing": [
        {
            "q": "What does tokenisation do in NLP?",
            "a": "Converts text to numbers",
            "b": "Splits text into individual words or sub-word units",
            "c": "Removes HTML tags",
            "d": "Translates text to another language",
            "correct": "b",
            "explanation": "Tokenisation breaks raw text into tokens (words, sentences, or sub-words)."
        },
        {
            "q": "What is TF-IDF used for?",
            "a": "Image classification",
            "b": "Measuring how important a word is in a document relative to a corpus",
            "c": "Generating random text",
            "d": "Training recurrent neural networks",
            "correct": "b",
            "explanation": "TF-IDF weights words by frequency in a document vs. rarity across documents."
        },
    ],

    # --------------------------------------------------------------- MongoDB
    "mongodb": [
        {
            "q": "What type of database is MongoDB?",
            "a": "Relational", "b": "Graph", "c": "Document-oriented NoSQL", "d": "Column-family",
            "correct": "c",
            "explanation": "MongoDB stores data as JSON-like BSON documents."
        },
        {
            "q": "Which method inserts a single document into a MongoDB collection?",
            "a": "db.collection.add()", "b": "db.collection.insertOne()",
            "c": "db.collection.put()", "d": "db.collection.create()",
            "correct": "b",
            "explanation": "`insertOne()` inserts a single document; `insertMany()` for multiple."
        },
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_exam(skills: list, num_questions: int = 10) -> list:
    """
    Generate a randomised quiz from the skills list.
    Returns a list of question dicts with keys:
      skill, question, options (list of 4), correct_index (0-3), explanation
    """
    pool = []

    # Collect questions for matched skills
    for skill in skills:
        skill_lower = skill.lower()
        if skill_lower in QUESTION_BANK:
            for q in QUESTION_BANK[skill_lower]:
                pool.append({
                    "skill":         skill_lower,
                    "question":      q["q"],
                    "options":       [q["a"], q["b"], q["c"], q["d"]],
                    "correct_index": ["a", "b", "c", "d"].index(q["correct"]),
                    "correct_letter": q["correct"].upper(),
                    "explanation":   q.get("explanation", ""),
                })

    # Fallback: if skills have no questions, pull from python/sql
    if not pool:
        for fallback_skill in ["python", "sql", "machine learning"]:
            for q in QUESTION_BANK.get(fallback_skill, []):
                pool.append({
                    "skill":         fallback_skill,
                    "question":      q["q"],
                    "options":       [q["a"], q["b"], q["c"], q["d"]],
                    "correct_index": ["a", "b", "c", "d"].index(q["correct"]),
                    "correct_letter": q["correct"].upper(),
                    "explanation":   q.get("explanation", ""),
                })

    random.shuffle(pool)
    return pool[:num_questions]


def get_available_skills() -> list:
    """Return a sorted list of skills that have questions in the bank."""
    return sorted(QUESTION_BANK.keys())
