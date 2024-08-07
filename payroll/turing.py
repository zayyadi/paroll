# def solution(a: [int], b: [int], x: int) -> int:
#     # write your solution here
#     diff_count = 0

#     for cards_a in a:
#         card_range = False

#         for cards_b in b:
#             if abs(cards_a - cards_b) <= x:
#                 card_range = True
#                 break

#         if not card_range:
#             diff_count += 1

#     return diff_count


# print(solution([1, 2, 3, 4], [2, 6, 78, 4, 5], 2))


def solution(s: str) -> str:
    # write your solution here
    colours = s.split()
    arranged_colours = [""] * len(colours)

    for colour in colours:
        lists = colour[:-1], colour[-1]
        name, position = lists
        position = int(position)
        arranged_colours[position - 1] = name

    return " ".join(arranged_colours)


color = "red3 green4 yellow5"
reorder = solution(color)
print(reorder)
