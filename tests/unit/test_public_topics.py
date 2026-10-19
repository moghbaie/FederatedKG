from itertools import combinations

from similarity.public_topics import topic_similarity


def test_topic_similarity_matches_ground_truth(public_profiles, ground_truth):
    topics = {r["researcher_id"]: set(r["published_topics"]) for r in public_profiles["researchers"]}
    for a, b in combinations(sorted(topics), 2):
        expected = ground_truth["topic_similarity"][f"{a}|{b}"]
        result = topic_similarity(topics[a], topics[b])
        assert result["score"] == expected["jaccard"]
        assert result["matched_topics"] == expected["matched_topics"]
        assert result["metric"].startswith("topic_similarity")
